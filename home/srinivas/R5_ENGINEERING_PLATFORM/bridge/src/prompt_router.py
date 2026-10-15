"""Format requests only; never load files or evaluate engineering content."""

import json

from .work_package import WorkPackage


class PromptRouter:
    """Stateless formatter preserving all accepted work package types."""

    def format(self, package: WorkPackage) -> str:
        """Preserve supplied content in a structured, explicit prompt."""
        return json.dumps(
            {
                "request_type": package.type,
                "work_package_id": package.id,
                "objective": package.objective,
                "rules": package.rules,
                "files": package.files,
                "prompt": package.prompt,
                "metadata": package.metadata,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
