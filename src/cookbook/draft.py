import re
import tomllib
from typing import Annotated, Self

import tomli_w
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from cookbook.units import MeasureSystem

SLUG_PATTERN = r"^[a-z0-9][a-z0-9_]*$"
SERVES_PATTERN = re.compile(
    r"^\s*(?:serves\s+|makes\s+)?[~≈]?\s*(?P<low>\d+)(?:\s*(?:-|–|—|to)\s*(?P<high>\d+))?"
    r"\s*(?P<unit>[a-z][a-z ]*?)?\s*(?:\(.*\))?\s*$",
    re.IGNORECASE,
)
SERVES_UNIT_WORDS = {"people", "person", "portions", "servings"}

type NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def ingredient_pair_to_mapping(value: object) -> object:
    """
    Accept an ingredient written as a ["quantity", "item"] pair as well as a table.

    The input is raw TOML or Python data of any shape, hence object; pydantic validates
    the result.
    """
    if isinstance(value, list | tuple) and len(value) == 2:
        return {"quantity": value[0], "item": value[1]}
    return value


class IngredientLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: str = ""
    item: str = Field(min_length=1)
    grams: float | None = Field(default=None, gt=0)


class IngredientSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = None
    items: list[Annotated[IngredientLine, BeforeValidator(ingredient_pair_to_mapping)]] = Field(
        min_length=1
    )


class Step(BaseModel):
    """One method step: a short heading ("Brown the chicken") and the instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: NonBlankText
    text: NonBlankText


class DraftImages(BaseModel):
    """File names of the pre-sized images, relative to the draft file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hero: str
    card: str
    hero_alt: str | None = None
    credit: str | None = None
    origin: str | None = None


class RecipeDraft(BaseModel):
    """
    A recipe as a TOML file: what recipe-db imports and the app exports.

    total_min defaults to the sum of the prep, cook and rest times that are given.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(pattern=SLUG_PATTERN)
    title: str = Field(min_length=1)
    url: str | None = None
    archive_url: str | None = None
    publication: str | None = None
    author: str | None = None
    serves: str | None = None
    measure_system: MeasureSystem = "uk"
    prep_min: int | None = Field(default=None, ge=0)
    cook_min: int | None = Field(default=None, ge=0)
    rest_min: int | None = Field(default=None, ge=0)
    total_min: int | None = Field(default=None, ge=0)
    intro: str | None = None
    tags: list[str] = []
    steps: list[Step] = Field(min_length=1)
    images: DraftImages | None = None
    sections: list[IngredientSection] = []

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, tags: list[str]) -> list[str]:
        normalised = [" ".join(tag.lower().split()) for tag in tags]
        return list(dict.fromkeys(tag for tag in normalised if tag))

    @model_validator(mode="after")
    def default_total(self) -> Self:
        parts = [self.prep_min, self.cook_min, self.rest_min]
        if self.total_min is None and any(part is not None for part in parts):
            object.__setattr__(self, "total_min", sum(part or 0 for part in parts))
        return self

    @classmethod
    def from_toml(cls, text: str) -> Self:
        return cls.model_validate(tomllib.loads(text))

    def to_toml(self) -> str:
        """
        Write the draft as TOML: scalars first, then steps, images and ingredient sections.

        An ingredient without a gram override is written as a ["quantity", "item"] pair.
        """
        data = self.model_dump(exclude_none=True, exclude={"images", "sections"})
        if self.images is not None:
            data["images"] = self.images.model_dump(exclude_none=True)
        data["sections"] = [
            {
                **({"name": section.name} if section.name is not None else {}),
                "items": [
                    [line.quantity, line.item]
                    if line.grams is None
                    else line.model_dump(exclude_none=True)
                    for line in section.items
                ],
            }
            for section in self.sections
        ]
        if not data["sections"]:
            del data["sections"]
        return tomli_w.dumps(data)


def parse_serves(text: str | None) -> tuple[int | None, int | None, str | None]:
    """
    Read a serves text into (minimum, maximum, yield unit).

    "2–4" is (2, 4, None); "~24 cookies" is (24, 24, "cookies"); "Serves 4" and
    "4 people" have no yield unit; text without a leading number gives (None, None, None).
    """
    match = SERVES_PATTERN.match(text or "")
    if match is None:
        return None, None, None
    low = int(match["low"])
    high = int(match["high"]) if match["high"] else low
    unit = match["unit"].strip().lower() if match["unit"] else None
    if unit in SERVES_UNIT_WORDS:
        unit = None
    return low, high, unit
