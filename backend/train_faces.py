import argparse
import shutil
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def iter_images(root: Path) -> Iterable[Path]:
	for path in sorted(root.rglob("*")):
		if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
			yield path


def person_name_from_image(path: Path) -> str:
	name = path.stem.strip()
	if not name:
		return "unknown"
	return name


def build_dataset(source_dir: Path, output_dir: Path, overwrite: bool = False) -> int:
	output_dir.mkdir(parents=True, exist_ok=True)
	count = 0

	for image_path in iter_images(source_dir):
		person_name = person_name_from_image(image_path)
		person_dir = output_dir / person_name
		person_dir.mkdir(parents=True, exist_ok=True)

		target_path = person_dir / image_path.name
		if target_path.exists() and not overwrite:
			stem = image_path.stem
			suffix = image_path.suffix
			index = 1
			while True:
				target_path = person_dir / f"{stem}_{index}{suffix}"
				if not target_path.exists():
					break
				index += 1

		shutil.copy2(image_path, target_path)
		count += 1

	return count


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Prepare a face dataset from loose image files. The image filename becomes the person name."
	)
	parser.add_argument("--source", required=True, help="Folder containing loose face images")
	parser.add_argument(
		"--output",
		default="faces",
		help="Output folder structured as faces/<person_name>/<image files>",
	)
	parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Overwrite files if the same name already exists",
	)
	args = parser.parse_args()

	source_dir = Path(args.source).expanduser().resolve()
	output_dir = Path(args.output).expanduser().resolve()

	if not source_dir.exists():
		raise SystemExit(f"Source folder does not exist: {source_dir}")

	count = build_dataset(source_dir, output_dir, overwrite=args.overwrite)
	print(f"Prepared {count} image(s) in {output_dir}")


if __name__ == "__main__":
	main()
