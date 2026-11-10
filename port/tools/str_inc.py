import sys, json
text = open(sys.argv[1]).read()
open(sys.argv[2], 'w').write('\n'.join(json.dumps(l + '\n') for l in text.split('\n')) + '\n')
