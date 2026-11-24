"""Create or remeasure the P0.5 examples with FreeCAD 1.1.3's Python."""

import argparse
import json
from pathlib import Path

import FreeCAD as App
import Part
import AssemblyApp  # registers the native assembly document type
import JointObject  # registers the distance and grounded joints


HERE = Path(__file__).resolve().parent
SEED = HERE.parent / "observation-study/cadworld_seed/fixtures/assemble/freecad-assemble-003.FCStd"
TOLERANCE_MM = 1e-6


def make_assembly(directory, distance):
    doc = App.openDocument(str(SEED))
    try:
        doc.Joint.Distance = distance
        doc.recompute()
        if doc.Assembly.solve() != 0:
            raise ValueError(f"FreeCAD could not solve the {distance} mm assembly")
        doc.recompute()
        doc.saveAs(str(directory / f"gap-{distance}mm.FCStd"))
    finally:
        App.closeDocument(doc.Name)


def measure_assembly(path):
    doc = App.openDocument(str(path))
    try:
        doc.recompute()
        joint = doc.Joint
        faces, names = [], []
        for component, elements in (joint.Reference1, joint.Reference2):
            names.append(f"{component.Name}.{elements[0]}")
            faces.append(component.Shape.getElement(elements[0]))
        if names != ["Box.Face2", "Box001.Face1"]:
            raise ValueError(f"Expected the original two faces, found {names}")
        gap = faces[0].distToShape(faces[1])[0]
        closest = doc.Box.Shape.distToShape(doc.Box001.Shape)[0]
        valid_solids = all(obj.Shape.isValid() and len(obj.Shape.Solids) == 1
                           for obj in (doc.Box, doc.Box001))
        return dict(joint_type=joint.JointType, grounded=doc.GroundedJoint.ObjectToGround.Name,
                    selected_faces=names, valid_single_solid_components=valid_solids,
                    stored_distance_mm=joint.Distance.Value, face_distance_mm=round(gap, 9),
                    closest_solid_distance_mm=round(closest, 9),
                    satisfies_5mm=abs(gap - 5) <= TOLERANCE_MM)
    finally:
        App.closeDocument(doc.Name)


def make_plate(directory, linked):
    doc = App.newDocument("CenterHole")
    try:
        plate = doc.addObject("Part::Box", "Plate")
        plate.Length, plate.Width, plate.Height = 40, 20, 4
        tool = doc.addObject("Part::Cylinder", "Drill")
        tool.Radius, tool.Height = 2, 4
        tool.Placement.Base = App.Vector(20, 10, 0)
        if linked:
            tool.setExpression("Placement.Base.x", "Plate.Length / 2")
        result = doc.addObject("Part::Cut", "DrilledPlate")
        result.Base, result.Tool = plate, tool
        doc.recompute()
        plate.Visibility = tool.Visibility = False
        name = "linked" if linked else "fixed"
        doc.saveAs(str(directory / f"plate-{name}.FCStd"))
    finally:
        App.closeDocument(doc.Name)


def measure_plate(path):
    doc = App.openDocument(str(path))
    try:
        states, shapes = [], []
        for length in (40, 60):
            doc.Plate.Length = length
            doc.recompute()
            shape = doc.DrilledPlate.Shape
            holes = [f.Surface for f in shape.Faces if isinstance(f.Surface, Part.Cylinder)]
            if len(holes) != 1 or len(shape.Solids) != 1 or not shape.isValid():
                raise ValueError("Expected a valid single solid with one cylindrical hole")
            center_x = holes[0].Center.x
            box = shape.BoundBox
            plate_center = (box.XMin + box.XMax) / 2
            states.append(dict(plate_length_mm=round(box.XLength, 9),
                               hole_center_x_mm=round(center_x, 9),
                               offset_from_plate_center_mm=round(abs(center_x - plate_center), 9)))
            shapes.append(shape.copy())
        return states, shapes
    finally:
        App.closeDocument(doc.Name)


def measure(directory):
    assembly_files = {"upstream_reference": SEED, "resaved_5mm": directory / "gap-5mm.FCStd",
                      "resaved_8mm": directory / "gap-8mm.FCStd"}
    assembly = {key: measure_assembly(path) for key, path in assembly_files.items()}
    linked, linked_shapes = measure_plate(directory / "plate-linked.FCStd")
    fixed, fixed_shapes = measure_plate(directory / "plate-fixed.FCStd")
    volume_differences = []
    for a, b in zip(linked_shapes, fixed_shapes):
        volume_differences.append(round(a.cut(b).Volume + b.cut(a).Volume, 9))
    return dict(freecad_version=".".join(App.Version()[:3]), numerical_tolerance_mm=TOLERANCE_MM,
                assemblies=assembly, plates=dict(linked=linked, fixed=fixed,
                symmetric_difference_volume_mm3_at_40_and_60=volume_differences))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", type=Path)
    parser.add_argument("--generate", action="store_true", help="Create the four models in an empty directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    directory = args.models.resolve()
    if args.generate:
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            parser.error("--generate requires an empty output directory")
        for distance in (5, 8):
            make_assembly(directory, distance)
        for linked in (True, False):
            make_plate(directory, linked)
    evidence = measure(directory)
    args.out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
