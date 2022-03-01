#!/usr/bin/env python3

import sys
from xml.etree.ElementTree import parse

import anybadge

thresholds = {30: 'red', 50: 'orange', 70: 'yellow', 100: 'green'}


def calc_coverage(covered, missed):
    return round(float(covered) / (float(missed) + float(covered)) * 100, 2)


def generate_coverage_badge():
    tree = parse(sys.argv[1])
    root = tree.getroot()
    for counter in root.findall("counter"):
        if counter.attrib['type'] == 'INSTRUCTION':
            coverage = calc_coverage(counter.attrib['covered'], counter.attrib['missed'])
            badge = anybadge.Badge("coverage", coverage, value_format="%.2f%%", thresholds=thresholds)
            badge.write_badge("coverage.svg")
            break


if __name__ == '__main__':
    assert len(sys.argv) > 1
    generate_coverage_badge()
