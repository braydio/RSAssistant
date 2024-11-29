# Move me to rsassistant/src/.

import argparse
from utils.sql_utils import get_table_data

def main():
    parser = argparse.ArgumentParser(description="Query database tables.")
    parser.add_argument("table_name", help="Name of the table to query.")
    parser.add_argument("--filters", nargs="*", help="Optional filters in key=value format.")
    parser.add_argument("--limit", type=int, help="Maximum number of rows to fetch.")

    args = parser.parse_args()
    filters = dict(arg.split("=") for arg in args.filters) if args.filters else None

    try:
        data = get_table_data(args.table_name, filters, args.limit)
        if data:
            for row in data:
                print(row)
        else:
            print(f"No data found in table '{args.table_name}' with filters {filters}.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()