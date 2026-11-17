"""Regenerate the Python gRPC stubs from protos/tunisovereign.proto.

Run from the repository root:   python grpc_service/generate_stubs.py

Run it again if you edit the .proto, or if Python complains about a protobuf
Gencode/Runtime version mismatch (the stubs must be generated with the grpcio-tools
installed in YOUR environment).
"""
import re
import sys
from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "grpc_service"


def main() -> int:
    rc = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{ROOT / 'protos'}",
            f"--python_out={OUT}",
            f"--grpc_python_out={OUT}",
            str(ROOT / "protos" / "tunisovereign.proto"),
        ]
    )
    if rc != 0:
        return rc
    # protoc emits `import tunisovereign_pb2 ...`; make it a package-relative import.
    grpc_file = OUT / "tunisovereign_pb2_grpc.py"
    text = grpc_file.read_text()
    text = re.sub(r"^import tunisovereign_pb2 as", "from . import tunisovereign_pb2 as", text, flags=re.M)
    grpc_file.write_text(text)
    print("Stubs generated in", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
