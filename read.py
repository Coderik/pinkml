from argparse import ArgumentParser

from inkml.reading import Reader

if __name__ == '__main__':
	parser = ArgumentParser(prog='Read coordinates from .inkml')
	parser.add_argument('input', type=str, help='Path to input file')

	args = parser.parse_args()

	reader = Reader()

	with open(args.input, 'r') as f:
		ink = reader.read(f.read())

	for index, trace in enumerate(ink.traces):
		print(f'trace #{index}')
		for x, y, t in zip(trace.channels['X'], trace.channels['Y'], trace.channels['T']):
			print(f'{x:.3f}, {y:.3f}, {t:.3f}')

		print()