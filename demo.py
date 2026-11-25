from pathlib import Path
from tempfile import TemporaryDirectory

from lab import Workflow


def main():
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'demo.sqlite'
        work = Workflow(path)
        work.start('other', ['room'])
        work.tick('other')
        work.start('new', ['projector', 'chairs', 'room'])
        for _ in range(5):
            print(Workflow(path).tick('new'))
        print('Reservations remaining:', work.held())


if __name__ == '__main__':
    main()
