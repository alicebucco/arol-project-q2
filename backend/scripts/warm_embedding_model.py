"""Download and validate the local embedding model before the API starts."""

import sys
from pathlib import Path

# Running a script directly makes ``scripts/`` the first import path. Add the
# backend directory so the sibling ``agents`` package is available as it is to
# uvicorn, whose working directory is /app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.manuals import MODEL_NAME, embedding_model


def main() -> None:
    """Populate HF_HOME and fail early if the embedding model is unusable."""

    model = embedding_model()
    dimension = model.get_embedding_dimension()
    print(f"Embedding model ready: {MODEL_NAME} ({dimension} dimensions)")


if __name__ == "__main__":
    main()
