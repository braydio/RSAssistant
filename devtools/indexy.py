# -- Put me in rsassistant/src/.


import ast
import re
import csv
import json


def extract_subsections(file_path):
    """Extracts subsection names from comments labeled with # ! -- Subsection Name."""
    subsections = []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for lineno, line in enumerate(file, start=1):
                # Update regex to match commented section titles
                match = re.match(r"#\s*! -- (.+)", line.strip())
                if match:
                    subsections.append({
                        "type": "subsection",
                        "name": match.group(1),
                        "start_line": lineno,
                        "end_line": None
                    })
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"Error extracting subsections: {e}")

    return subsections


def generate_function_index(file_path):
    """Generates an index of all functions (sync and async) in a Python file."""
    function_index = []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            code = file.read()

        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                function_index.append({
                    "type": "async def" if isinstance(node, ast.AsyncFunctionDef) else "def",
                    "name": node.name,
                    "start_line": node.lineno,
                    "end_line": getattr(node, 'end_lineno', None)
                })

        return function_index

    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")

    return []


def export_to_json(entries, output_path):
    """Exports the combined index to a JSON file."""
    try:
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(entries, file, indent=4)
        print(f"Exported data to JSON file: {output_path}")
    except Exception as e:
        print(f"Error exporting to JSON: {e}")


def export_to_csv(entries, output_path):
    """Exports the combined index to a CSV file."""
    try:
        with open(output_path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["type", "name", "start_line", "end_line"])
            writer.writeheader()
            writer.writerows(entries)
        print(f"Exported data to CSV file: {output_path}")
    except Exception as e:
        print(f"Error exporting to CSV: {e}")


if __name__ == "__main__":
    file_path = input("Enter the path to the Python file: ")

    # Extract subsections and functions
    subsections = extract_subsections(file_path)
    functions = generate_function_index(file_path)

    # Combine and sort all entries by start line
    combined_entries = sorted(subsections + functions, key=lambda x: x["start_line"])

    if combined_entries:
        print(f"\nIndex of functions and subsections in {file_path}:\n")
        for entry in combined_entries:
            print(f"{entry['type']:<12} {entry['name']:<30} {entry['start_line']:<12} {entry['end_line'] or 'Unknown':<12}")

        # Export options
        json_output_path = file_path.replace(".py", "_index.json")
        csv_output_path = file_path.replace(".py", "_index.csv")

        export_to_json(combined_entries, json_output_path)
        export_to_csv(combined_entries, csv_output_path)

    else:
        print(f"No functions or subsections found in {file_path} or the file could not be processed.")
