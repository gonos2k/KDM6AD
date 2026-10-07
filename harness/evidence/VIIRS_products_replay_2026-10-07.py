#!/usr/bin/env python3
"""Offline replay of generation-pinned HDF5 range receipts, with no network.

Missing byte ranges fail; we never synthesize unobserved chunks or whole files.
"""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


class CachedFile:
    def __init__(self, root, product):
        self.size = int(product['gcs_object']['size'])
        self.pos = 0
        self.blocks = {}
        for record in product['range_transfer']['ranges']:
            if not (0 <= record['start'] <= record['end'] < self.size) or record['bytes'] != record['end']-record['start']+1:
                raise ValueError('invalid declared range endpoints/length')
            data = (root / record['raw_file']).read_bytes()
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('range receipt bytes differ')
            if record['content_range'] != f"bytes {record['start']}-{record['end']}/{self.size}":
                raise ValueError('range receipt offset/size differs')
            self.blocks[record['start']] = data
        self.starts = sorted(self.blocks)

    def seek(self, offset, whence=0):
        if whence == 0:
            target = offset
        elif whence == 1:
            target = self.pos + offset
        elif whence == 2:
            target = self.size + offset
        else:
            raise ValueError('invalid whence')
        if target < 0:
            raise ValueError('negative seek')
        self.pos = target
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        end = self.size if n < 0 else min(self.size, self.pos+n)
        output = bytearray()
        while self.pos < end:
            candidates = [s for s in self.starts if s <= self.pos < s+len(self.blocks[s])]
            if not candidates:
                raise ValueError(f'unobserved byte range at {self.pos}; cannot replay')
            start = candidates[-1]
            block = self.blocks[start]
            take = min(end-self.pos, start+len(block)-self.pos)
            output.extend(block[self.pos-start:self.pos-start+take])
            self.pos += take
        return bytes(output)

    def readable(self):
        return True

    def seekable(self):
        return True

    def flush(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--packet-root', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.receipt.read_text())
    checked = 0
    for product in result['products'].values():
        handle = CachedFile(args.packet_root, product)
        row, col = product['target_index_zero_based']
        with h5py.File(handle, 'r') as d:
            for name, field in product['fields'].items():
                variable = d[name]
                if list(variable.shape) != field['shape'] or str(variable.dtype) != field['dtype']:
                    raise ValueError(f'dataset schema differs: {name}')
                if 'raw_value' not in field:
                    continue
                if variable.shape == ():
                    actual = variable[()]
                elif variable.shape == (1,):
                    actual = variable[0]
                elif variable.ndim == 2:
                    actual = variable[row, col]
                else:
                    actual = variable[row, col, :]
                if np.asarray(actual).tolist() != field['raw_value']:
                    raise ValueError(f'raw sample differs: {name}')
                checked += 1
    print(f'{checked} raw target values replayed exactly from cached original HDF5 ranges; no network')


if __name__ == '__main__':
    main()
