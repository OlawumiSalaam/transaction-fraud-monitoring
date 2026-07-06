"""Measured vs modelled-estimate labelling for offline evaluation.

Rule of record: no metric that requires production users or real outcomes
is claimed as measured evidence. Model metrics on synthetic PaySim are *measured
on synthetic distributions* but a *modelled estimate* of real-world performance;
grounding integrity is genuinely *measured* (the evidence set is known on synthetic
cases). Every reported number carries its epistemic status so nothing reads as an
unqualified performance claim.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Label(StrEnum):
    MEASURED = "measured"
    MODELLED_ESTIMATE = "modelled_estimate"


class LabelledValue(BaseModel):
    """A reported value tagged with its epistemic status."""

    model_config = ConfigDict(frozen=True)

    value: float | int | str | bool | None
    label: Label
    note: str | None = None


def measured(value: float | int | str | bool | None, note: str | None = None) -> LabelledValue:
    return LabelledValue(value=value, label=Label.MEASURED, note=note)


def modelled(value: float | int | str | bool | None, note: str | None = None) -> LabelledValue:
    return LabelledValue(value=value, label=Label.MODELLED_ESTIMATE, note=note)
