import json
import argparse

def parse_config_json(file):
    with open(file, "r") as f:
        data = json.load(f)
    return data

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Pardus Automatized Unofficial Package Builder")
    argparser.add_argument("config", help="Build configuration file (json)")
    argparser.add_argument("-p", "--no-prompt", action="store_true", help="Build package directly without interactive prompts")

    args = argparser.parse_args()
    edit_source_flag = args.no_prompt
    build_configuration = parse_config_json(args.config)
