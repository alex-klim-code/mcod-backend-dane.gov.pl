"""Run the same Daphne ASGI server as Channels runserver, without dev checks."""

from daphne.cli import CommandLineInterface


if __name__ == "__main__":
    CommandLineInterface.entrypoint()
