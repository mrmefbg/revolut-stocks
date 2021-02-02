import argparse
import os
import logging

from libs.exchange_rates import populate_exchange_rates
from libs.calculations import calculate_sales, calculate_dividends, calculate_win_loss
from libs.utils import get_parsers, get_unsupported_activity_types
from libs.parsers import *
from libs.csv import export_statements, export_app8_part1, export_app5_table2, export_app8_part4_1
from libs.xml import export_to_xml

logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")
logger = logging.getLogger("main")

parser = argparse.ArgumentParser(description="Revolut stock calculator for NAP.")
parser.add_argument("-i", dest="input_dir", help="Directory containing Revolut statement files(in pdf format).", required=False)
parser.add_argument(
    "-o",
    dest="output_dir",
    help="Output directory for csv files. Directory will be populated with NAP calculations and verification documents in csv format.",
    required=True,
)
parser.add_argument("-b", dest="use_bnb", help="Use BNB online service as exchange rates source.", action="store_true")
parser.add_argument("-v", dest="verbose", help="Enable verbose output.", action="store_true")
parser.add_argument(
    "-p",
    dest="parsers",
    action="append",
    help=(
        "Parsers to use for statement processing.\n"
        "Multiple parsers are supported by repeating the argument for each parser like so:\n"
        "-p <parser#1_name>:<parser#1_input_dir> -i <parser#2_name>:<parser#2_input_dir>.\n"
        "In case a single parser is provided the input directory argument(-i) would be used as input directory for that parser.\n"
        "Default: [revolut].\n"
    ),
    required=False,
)
parsed_args = parser.parse_args()

if parsed_args.verbose:
    logging.getLogger("calculations").setLevel(level=logging.DEBUG)
    logging.getLogger("exchange_rates").setLevel(level=logging.DEBUG)
    logging.getLogger("parsers").setLevel(level=logging.DEBUG)


def for_each_parser(func, iter_arg_name, statements, combine, **kwargs):
    if combine:
        parser_statements = []
        for parser, statements in statements.items():
            if statements is not None:
                parser_statements.extend(statements)

        return func(**{iter_arg_name: parser_statements}, **kwargs)
    else:
        result = {}
        for parser, statements in statements.items():
            result[parser] = func(**{iter_arg_name: statements}, **kwargs)

        return result


def main():
    parsers, unsupported_parsers = get_parsers(globals(), parsed_args.parsers, parsed_args.input_dir)

    if len(unsupported_parsers) > 0:
        logger.error(f"Unsupported parsers found: {unsupported_parsers}.")
        raise SystemExit(1)

    logger.info(f"Parsing statement files.")
    statements = {}
    for parser_name, parser_instance in parsers:
        statements[parser_name] = parser_instance.parse()

        if not statements[parser_name]:
            logger.error(f"Not activities found with parser[{parser_name}]. Please, check your statement files.")
            raise SystemExit(1)

    logger.info(f"Generating [statements.csv] file.")
    for_each_parser(export_statements, "statements", statements, True, filename=os.path.join(parsed_args.output_dir, "statements.csv"))

    logger.info(f"Populating exchange rates.")
    for_each_parser(populate_exchange_rates, "statements", statements, False, use_bnb=parsed_args.use_bnb)

    logger.info(f"Calculating dividends information.")
    dividends = for_each_parser(calculate_dividends, "statements", statements, False)

    logger.info(f"Generating [app8-part4-1.csv] file.")
    for_each_parser(export_app8_part4_1, "dividends", dividends, True, filename=os.path.join(parsed_args.output_dir, "app8-part4-1.csv"))

    parsers_calculations = None
    sales = None
    unsupported_activity_types = get_unsupported_activity_types(globals(), statements)

    if len(unsupported_activity_types) == 0:
        logger.info(f"Calculating sales information.")
        parsers_calculations = for_each_parser(calculate_sales, "statements", statements, False)

        logger.info(f"Generating [app5-table2.csv] file.")
        sales = {parser_name: parser_calculations[0] for parser_name, parser_calculations in parsers_calculations.items()}
        for_each_parser(
            export_app5_table2,
            "sales",
            sales,
            True,
            filename=os.path.join(parsed_args.output_dir, "app5-table2.csv"),
        )

    logger.info(f"Generating [dec50_2020_data.xml] file.")
    aggregated_data = {}
    for parser_name in dividends.keys():
        aggregated_data[parser_name] = export_to_xml(
            os.path.join(parsed_args.output_dir, "dec50_2020_data.xml"),
            dividends[parser_name],
            parsers_calculations[parser_name] if parsers_calculations is not None else None,
        )

    logger.info(f"Generating [app8-part1.csv] file.")
    for_each_parser(export_app8_part1, "purchases", aggregated_data, True, filename=os.path.join(parsed_args.output_dir, "app8-part1.csv"))

    if sales is not None:
        win_loss = calculate_win_loss(sales)
        logger.info(f"Profit/Loss: {win_loss} lev.")

    if unsupported_activity_types:
        logger.warning(f"Statements contain unsupported activity types: {unsupported_activity_types}. Only dividends related data was calculated.")


if __name__ == "__main__":
    main()