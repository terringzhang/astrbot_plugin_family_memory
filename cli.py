"""Local operator CLI. Does not contact QQ or any provider. Run with plugin stopped."""
import argparse
import json
from pathlib import Path

from .engine import MemoryEngine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--config',required=True,help='JSON configuration, no API keys needed')
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('stats');sub.add_parser('sync')
    for action in ['search','remember','correct','forget']:
        p=sub.add_parser(action)
        p.add_argument('--platform',required=True);p.add_argument('--self-id',required=True);p.add_argument('--sender',required=True)
        if action in ['search','remember','correct']:p.add_argument('text')
        if action in ['correct','forget']:p.add_argument('--id',required=True)
        if action=='remember':p.add_argument('--family',action='store_true')
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    engine=MemoryEngine(args.root,config)
    try:
        if args.action=='stats':result=engine.stats()
        elif args.action=='sync':engine.maintenance();result=engine.stats()
        else:
            p=engine.policy.resolve(args.platform,args.self_id,args.sender)
            if args.action=='search':result=engine.search(p,args.text)
            elif args.action=='forget':engine.forget(p,args.id);result={'forgotten':args.id}
            else:
                import uuid
                shared=args.family if args.action=='remember' else engine.get(p,args.id)['ns']=='family'
                sid=engine.capture(p,'operator:'+uuid.uuid4().hex,args.text,share=shared)
                refs=[{'id':sid,'quote':args.text}]
                if args.action=='correct':engine.correct(p,args.id,args.text,refs);result={'corrected':args.id}
                else:result={'created':engine.remember(p,args.text,refs,shared=shared)}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:engine.close()


if __name__=='__main__':main()
