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
if method != 'GET':
    print('unexpected mutation', file=sys.stderr)
    sys.exit(99)
with open(os.environ['TEST_RESPONSES']) as stream:
    responses = json.load(stream)
if path not in responses:
    print('unexpected endpoint', file=sys.stderr)
    sys.exit(99)
response = responses[path]
if '_sequence' in response:
    # Successive calls walk the sequence; the last entry repeats.
    state_file = os.environ['TEST_RESPONSES'] + '.count'
    counts = {}
    if os.path.exists(state_file):
        with open(state_file) as stream:
            counts = json.load(stream)
    index = counts.get(path, 0)
    counts[path] = index + 1
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
