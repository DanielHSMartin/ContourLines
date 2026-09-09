"""Check the VRT kernels embedded in contour_lines_algorithm.py.

GDAL rejects a KernelFilteredSource whose coefficient count is not
Size*Size, which breaks only the smoothing level using that kernel.
That is exactly what happened to the 13x13 kernel of the "High" level.

The coefficients are written as adjacent string literals, so the source
is parsed instead of grepped: the parser joins them the same way Python
does at runtime.
"""
import ast
import os
import re

SRC = os.path.join(os.path.dirname(__file__), '..',
                   'contour_lines_algorithm.py')


def kernels():
    tree = ast.parse(open(SRC, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for m in re.finditer(r'<Size>(\d+)</Size>\s*<Coefs>([^<]*)</Coefs>',
                                 node.value):
                yield int(m.group(1)), [float(v) for v in m.group(2).split()]


def test_kernels():
    found = dict(kernels())
    assert len(found) == 4, f'expected 4 kernels, found {len(found)}'
    for size, values in found.items():
        assert len(values) == size * size, \
            f'kernel {size}x{size}: {len(values)} coefs, expected {size*size}'
        assert abs(sum(values) - 1.0) < 1e-4, \
            f'kernel {size}x{size}: sums to {sum(values)}'

    # A bigger kernel must smooth more, i.e. have a smaller centre weight.
    # Without this, "High" (13x13) is just a copy of "Medium" (7x7).
    centre = {s: v[len(v) // 2] for s, v in found.items()}
    assert centre[13] < centre[7] < centre[3], \
        f'smoothing levels do not progress: {centre}'


if __name__ == '__main__':
    test_kernels()
    print('ok')
