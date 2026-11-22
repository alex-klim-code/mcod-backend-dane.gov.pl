"""Run real Daphne with startup diagnostics, without Django's dev checks."""

import os
import sys
import traceback


def main():
    # This precedes even the diagnostics/Daphne imports, proving this file ran.
    print(
        "[mcod-admin] event=entrypoint_enter pid={} file={}".format(
            os.getpid(), os.path.abspath(__file__)
        ),
        file=sys.stderr,
        flush=True,
    )
    os.environ.setdefault("MCOD_STARTUP_DIAGNOSTICS", "1")
    from scripts.replit import startup_diagnostics as diagnostics

    try:
        diagnostics.event(
            "python_enter",
            executable=sys.executable,
            settings_module=os.environ.get("DJANGO_SETTINGS_MODULE", "mcod.settings.replit"),
        )
        diagnostics.arm_traceback_timer()
        diagnostics.event("daphne_cli_import_begin")
        from daphne import cli as daphne_cli
        from daphne.server import Server

        diagnostics.event("daphne_cli_import_complete", module_file=daphne_cli.__file__)

        class ObservedServer(Server):
            bind_failed = False

            def __init__(self, *args, **kwargs):
                # Daphne constructs Server only AFTER importing the ASGI app.
                diagnostics.event("asgi_application_import_complete")
                super().__init__(*args, **kwargs)

            def listen_success(self, port):
                super().listen_success(port)
                address = port.getHost()
                diagnostics.event("listening", host=address.host, port=address.port)
                diagnostics.cancel_traceback_timer()

            def listen_error(self, failure):
                self.bind_failed = True
                diagnostics.event("listen_failed", exception_type=failure.type.__name__)
                print(failure.getTraceback(), file=sys.stderr, flush=True)
                super().listen_error(failure)

        class ObservedCLI(daphne_cli.CommandLineInterface):
            server_class = ObservedServer

        diagnostics.event("daphne_entrypoint_begin")
        cli = ObservedCLI()
        cli.run(sys.argv[1:])
        if cli.server is not None and cli.server.bind_failed:
            # Legacy Daphne otherwise returns 0 after a failed listen.
            raise RuntimeError("Daphne could not open its listening socket; see listen_failed")
        diagnostics.event("daphne_entrypoint_return", exit_code=0)
    except BaseException as exc:
        previous_stage = diagnostics.last_stage()
        diagnostics.event(
            "initialization_exit",
            last_stage=previous_stage,
            exception_type=type(exc).__name__,
        )
        raise
    finally:
        diagnostics.cancel_traceback_timer()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Includes failures before Django has configured logging. No locals/env.
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)
