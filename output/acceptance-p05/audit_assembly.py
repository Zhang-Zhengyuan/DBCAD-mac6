"""Run CADWorld's published host-side evaluator on four local FCStd files."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
SEED = HERE.parent / "observation-study/cadworld_seed"
REVISION = "5e9529ff984b5426a5c194b94a09dc84cbe7fa7a"
TASK = "freecad-assemble-003"
CHECKSUMS = {
    "getters/freecad.py": "45c931d3c8b9bd8abf8d08d2270cf212e6c1ad4e84141ed7cc68663dd3468211",
    "metrics/freecad.py": "4c8fc2ec19a7591d93b5081a328810e8a71d45078c11f283ecb290625eedbf89",
    "metrics/freecad_assemble.py": "0a4628c0eaa489a259adc218f09992f5910980af95e8a8486235f698ce369285",
    "metrics/freecad_cam.py": "0217566755a01f08b6a5be557091ad5d49a318dc2d90643b51618be34d5506b3",
}


def prepare_evaluator(staging, source):
    for name, digest in CHECKSUMS.items():
        path = f"desktop_env/evaluators/{name}"
        if source:
            content = (source / path).read_bytes()
        else:
            url = f"https://raw.githubusercontent.com/Zdong104/CADWORLD/{REVISION}/{path}"
            with urlopen(url, timeout=45) as response:
                content = response.read()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Upstream checksum mismatch for {name}")
        dest = staging / name
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(content)


def audit(staging, models, source):
    prepare_evaluator(staging, source)
    sys.path.insert(0, str(staging))
    from getters.freecad import get_freecad_model_info
    from metrics.freecad_assemble import check_freecad_assemble_model, check_freecad_assemble_model_detailed

    task_bytes = (SEED / "examples/assemble" / f"{TASK}.json").read_bytes()
    if hashlib.sha256(task_bytes).hexdigest() != "a3387c915f85ea36141f4f80f6114dd94cfef3f3e0f07230e46b631fb4c43360":
        raise ValueError("Task definition changed")
    evaluator = json.loads(task_bytes)["evaluator"]
    if evaluator["func"] != "check_freecad_assemble_model" or evaluator["result"]["type"] != "freecad_model_info":
        raise ValueError("Unexpected evaluator")
    rules = evaluator["expected"]["rules"]
    candidates = {
        "upstream_precondition": SEED / "fixtures/precondition" / f"{TASK}-precondition.FCStd",
        "upstream_reference": SEED / "fixtures/assemble" / f"{TASK}.FCStd",
        "resaved_5mm": models / "gap-5mm.FCStd",
        "resaved_8mm": models / "gap-8mm.FCStd",
    }
    rows = {}
    for key, file in candidates.items():
        content = file.read_bytes()
        # Only substitute the VM file transport; pass the original config to the getter.
        files = {evaluator["result"]["path"]: content}
        env = SimpleNamespace(controller=SimpleNamespace(get_file=files.get), cache_dir=str(staging / key))
        model = get_freecad_model_info(env, evaluator["result"])
        score = check_freecad_assemble_model(model, rules)
        detailed = check_freecad_assemble_model_detailed(model, rules)
        if not model.get("exists") or score != detailed["score"]:
            raise ValueError(f"Extraction or scorer mismatch for {key}")
        assembly = model["assembly"]
        rows[key] = dict(sha256=hashlib.sha256(content).hexdigest(), score=score, checks=detailed["checks"],
                         extracted_joint_counts=assembly["joint_counts"],
                         extracted_distance_joint_mm=[j["distance"] for j in assembly["joints"]
                                                      if j["type"] == "Distance Joint"])
    return dict(cadworld_revision=REVISION, task=TASK, active_rules=rules, candidates=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cadworld-source", type=Path, help="Use files from this CADWorld checkout offline")
    parser.add_argument("--models", type=Path, default=HERE / "models")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        result = audit(Path(temp), args.models, args.cadworld_source)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
