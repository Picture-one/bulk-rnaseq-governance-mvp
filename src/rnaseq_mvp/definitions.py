from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from rnaseq_mvp.models import (
    DatasetDefinition,
    MethodDefinition,
    ReferenceDefinition,
    StageDefinition,
    ValidationPolicy,
)

ModelType = TypeVar("ModelType", bound=BaseModel)


def _load_collection(
    directory: Path,
    model_type: type[ModelType],
    identifier_field: str,
) -> dict[str, ModelType]:
    loaded: dict[str, ModelType] = {}

    paths = sorted(
        [
            *directory.glob("*.yaml"),
            *directory.glob("*.yml"),
        ]
    )

    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        model = model_type.model_validate(payload)
        identifier = str(getattr(model, identifier_field))

        if identifier in loaded:
            raise ValueError(f"duplicate {identifier_field}: {identifier}")

        loaded[identifier] = model

    return loaded


@dataclass(frozen=True)
class DefinitionRegistry:
    stages: dict[str, StageDefinition]
    datasets: dict[str, DatasetDefinition]
    references: dict[str, ReferenceDefinition]
    methods: dict[str, MethodDefinition]
    validations: dict[str, ValidationPolicy]

    @classmethod
    def load(cls, root: Path) -> DefinitionRegistry:
        definitions_root = root / "definitions"

        if not definitions_root.is_dir():
            definitions_root = root

        registry = cls(
            stages=_load_collection(
                definitions_root / "stages",
                StageDefinition,
                "stage_id",
            ),
            datasets=_load_collection(
                definitions_root / "datasets",
                DatasetDefinition,
                "dataset_id",
            ),
            references=_load_collection(
                definitions_root / "references",
                ReferenceDefinition,
                "reference_profile_id",
            ),
            methods=_load_collection(
                definitions_root / "methods",
                MethodDefinition,
                "method_profile_id",
            ),
            validations=_load_collection(
                definitions_root / "validation",
                ValidationPolicy,
                "validation_policy_id",
            ),
        )
        registry._validate_cross_references()
        return registry

    def _validate_cross_references(self) -> None:
        for stage in self.stages.values():
            if stage.dataset_id not in self.datasets:
                raise ValueError(f"unknown dataset_id: {stage.dataset_id}")

            if stage.reference_profile_id not in self.references:
                raise ValueError(
                    f"unknown reference_profile_id: {stage.reference_profile_id}"
                )

            if stage.method_profile_id not in self.methods:
                raise ValueError(
                    f"unknown method_profile_id: {stage.method_profile_id}"
                )

            if stage.validation_policy_id not in self.validations:
                raise ValueError(
                    f"unknown validation_policy_id: {stage.validation_policy_id}"
                )

            dataset = self.datasets[stage.dataset_id]
            known_sample_ids = {sample.sample_id for sample in dataset.samples}

            for sample_id in stage.sample_ids:
                if sample_id not in known_sample_ids:
                    raise ValueError(
                        f"unknown sample_id for stage {stage.stage_id}: {sample_id}"
                    )

    def stage(self, stage_id: str) -> StageDefinition:
        return self.stages[stage_id]

    def dataset(self, dataset_id: str) -> DatasetDefinition:
        return self.datasets[dataset_id]

    def reference(self, reference_profile_id: str) -> ReferenceDefinition:
        return self.references[reference_profile_id]

    def method(self, method_profile_id: str) -> MethodDefinition:
        return self.methods[method_profile_id]

    def validation(self, policy_id: str) -> ValidationPolicy:
        return self.validations[policy_id]
