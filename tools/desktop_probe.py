#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from qtranslate.desktop.capabilities import collect_capabilities

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--report');args=p.parse_args()
    report=collect_capabilities().to_dict()
    if args.report:
        out=Path(args.report);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
