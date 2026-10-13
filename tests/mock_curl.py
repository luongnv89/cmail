#!/usr/bin/env python3
"""Fixture-only curl replacement. Unknown operations fail; no network access."""
import json
import os
import sys

args = sys.argv[1:]
method = args[args.index('-X') + 1] if '-X' in args else 'GET'
url = next((arg for arg in args if arg.startswith('https://')), '')
path = url.removeprefix('https://api.cloudflare.com/client/v4')
settings = []
for flag in ('--max-time', '--connect-timeout'):
    if flag in args:
        settings.append(flag.removeprefix('--') + '=' + args[args.index(flag)+1])
with open(os.environ['TEST_CALLS'], 'a') as stream:
    stream.write(method+' '+path+' '+' '.join(settings)+'\n')
if '-d' in args and os.environ.get('TEST_PAYLOADS'):
    with open(os.environ['TEST_PAYLOADS'], 'a') as stream:
        stream.write(json.dumps({'method': method, 'path': path, 'body': json.loads(args[args.index('-d')+1])})+'\n')
with open(os.environ['TEST_RESPONSES']) as stream:
    responses = json.load(stream)
# GET fixtures are keyed by path. A mutation is allowed only by an explicit
# 'METHOD path' fixture; any other write fails as an unexpected mutation.
key = path if method == 'GET' else method + ' ' + path
if method != 'GET' and key not in responses:
    print('unexpected mutation', file=sys.stderr)
    sys.exit(99)
if key not in responses:
    print('unexpected endpoint', file=sys.stderr)
    sys.exit(99)
response = responses[key]
if '_sequence' in response:
    # Successive calls walk the sequence; the last entry repeats.
    state_file = os.environ['TEST_RESPONSES'] + '.count'
    counts = {}
    if os.path.exists(state_file):
        with open(state_file) as stream:
            counts = json.load(stream)
    index = counts.get(key, 0)
    counts[key] = index + 1
    with open(state_file, 'w') as stream:
        json.dump(counts, stream)
    response = response['_sequence'][min(index, len(response['_sequence']) - 1)]
response = dict(response)
status = response.pop('_status', 200)
body = response.pop('_body', None)
if '-fsS' in args and status >= 400:
    sys.exit(22)
print(body if body is not None else json.dumps(response), end='')
if '-w' in args:
    print('\n'+str(status), end='')
