"""Compare two interpretations of five paired expert scores in neuralCAD-Edit."""

import argparse
import hashlib
import json
import statistics
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

import bson  # from pymongo


REVISION = "b29220c3ccceecd9188ab42f1688e4e6bf5d7a7d"
PREFIX = "edit_192_external/mongita_db/v2_db."
URL = f"https://huggingface.co/datasets/autodesk/neuralCAD-Edit/resolve/{REVISION}/edit_192_external.zip"
# ZIP local headers and central directory at REVISION give these raw DEFLATE slices.
COMPRESSED_MEMBERS = {
    "ratings/$.data": (4770459259, 283072), "ratings/$.file_attrs": (4770742688, 45435),
    "edits/$.data": (4769950836, 494849), "edits/$.file_attrs": (4770446038, 12450),
    "requests/$.data": (6016738971, 804115), "requests/$.file_attrs": (6017543445, 2600),
    "users/$.data": (4770788898, 1537), "users/$.file_attrs": (4770790788, 452),
}
# The leaderboard notebook explicitly excludes one test account.
TEST_RATER_SHA = "7deab8f8ba0ce33d27b2636b7fe5f9b4961375e8c49a79fc188b233e41b46441"
TABLE_HASHES = {
    "ratings": ("f8d0c057859d86bca7a3ad26ec3753abb93503348fc4bb8ee630b7a83522cf62",
                "a35f08a4951397c53ac3bd07a47ca1d81a4846776a01c5894d3c39e3bbe24046"),
    "edits": ("39625b60ff1ef3bbad46ace8100a804843b15e5ed1b9f47f2429be7a0974ec0d",
              "5f0c5bb8c9ef71ca4842090928798d7c078eced9dbce409bddbe665dbe3741cd"),
    "requests": ("674f453fda8c9cae3ba8992adbb2c00fa30573b76c4b8ddd0d47ad9e9beb0a7e",
                 "e77aa37bb26d0d0701a0e4f596ea4ef70de387a4c1ee9a397217c912a4828449"),
    "users": ("087441acef8fd0c8fce37a9bc1a20f8ac0e98c44d29b583519621168026d01f6",
              "f19349603170d4c2a1a4d411b8bcef54865b0da5e4891be51f1f43b18ca6494c"),
}


def read_public_member(name):
    offset, size = COMPRESSED_MEMBERS[name.removeprefix(PREFIX)]
    end = offset + size - 1
    request = Request(f"{URL}?member_offset={offset}", headers={"Range": f"bytes={offset}-{end}"})
    with urlopen(request, timeout=60) as response:
        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/6029961729":
            raise ValueError("Server did not return the requested dataset range. Supply the original ZIP instead.")
        compressed = response.read(size + 1)
    if len(compressed) != size:
        raise ValueError("Incomplete dataset member")
    return zlib.decompress(compressed, -15)


def documents(read_member, table):
    # Mongita's live index excludes superseded records from its append-only data.
    path = f"{PREFIX}{table}/"
    data = read_member(path + "$.data")
    index = read_member(path + "$.file_attrs")
    if (hashlib.sha256(data).hexdigest(), hashlib.sha256(index).hexdigest()) != TABLE_HASHES[table]:
        raise ValueError(f"Unexpected dataset revision or corrupt {table} table")
    for key, offset in bson.decode(index)["loc_idx"].items():
        length, = struct.unpack_from("<i", data, offset)
        record = bson.decode(data[offset:offset + length])
        if str(record["_id"]) != key:
            raise ValueError(f"Index mismatch in {table}")
        yield record


def analyze(read_member):
    people = {row["_id"] for row in documents(read_member, "users") if row["is_human"]}
    requestors = {row["_id"]: row["user"] for row in documents(read_member, "requests")}
    edits = {}
    for row in documents(read_member, "edits"):
        author = row["user"]
        group = author
        if author in people:
            group = "human requestor" if author == requestors[row["request"]] else "human baseline"
        edits[row["_id"]] = group

    by_edit = defaultdict(dict)
    for row in documents(read_member, "ratings"):
        user = row["user"]
        if "private" not in user or hashlib.sha256(user.encode()).hexdigest() == TEST_RATER_SHA:
            continue
        raters = by_edit[row["edit"]]
        if user in raters or row["edit"] not in edits:
            raise ValueError("Duplicate paired rating or unknown edit")
        pair = (row.get("score_instr"), row.get("score_quality"))
        if any(v is not None and v not in range(1, 8) for v in pair):
            raise ValueError("Unexpected rating scale")
        raters[user] = pair

    def counts():
        return dict(edits=0, paper_pass_all=0, complete_five=0, paper_pass_complete=0,
                    paired_majority_pass=0, paper_only=0, paired_only=0)

    totals = counts()
    groups = defaultdict(counts)
    panel_sizes = Counter()
    witnesses = []
    for edit, group in edits.items():
        pairs = list(by_edit[edit].values())
        instr = [a for a, _ in pairs if a is not None]
        quality = [b for _, b in pairs if b is not None]
        # Raw-scale equivalents of the two defaults in the published notebook.
        medians = [statistics.median(instr or [2]), statistics.median(quality or [1])]
        paper_pass = min(medians) >= 5
        complete = [p for p in pairs if None not in p]
        panel_sizes[len(complete)] += 1
        use = len(pairs) == len(complete) == 5
        votes = sum(min(p) >= 5 for p in complete)
        joint_pass = votes >= 3
        for group_counts in (groups[group], totals):
            group_counts["edits"] += 1
            group_counts["paper_pass_all"] += paper_pass
            if use:
                group_counts["complete_five"] += 1
                group_counts["paper_pass_complete"] += paper_pass
                group_counts["paired_majority_pass"] += joint_pass
                group_counts["paper_only"] += paper_pass and not joint_pass
                group_counts["paired_only"] += joint_pass and not paper_pass
        if use and paper_pass and not joint_pass:
            witnesses.append(dict(edit_sha256=hashlib.sha256(str(edit).encode()).hexdigest(),
                                  editor=group, anonymous_pairs=sorted(complete),
                                  dimension_medians=medians, individual_double_pass=votes))
    witnesses.sort(key=lambda x: (x["individual_double_pass"], x["edit_sha256"]))
    return dict(dataset_revision=REVISION, distinct_requests=len(requestors), totals=totals,
                complete_pairs_per_edit=dict(sorted(panel_sizes.items())), by_editor=dict(sorted(groups.items())),
                disagreements=witnesses)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", nargs="?", type=Path, help="Local edit_192_external.zip (default: fetch eight members)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.zip:
        with ZipFile(args.zip) as dataset:
            results = analyze(dataset.read)
    else:
        results = analyze(read_public_member)
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
