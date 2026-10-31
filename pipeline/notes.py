"""Grammar notes ("formNote") written from Stanza's morphological features, in the three UI
languages. A fixed table rather than the AI: the same form always gets the same note, and a
reviewer can check the table once instead of every note."""

# Universal Dependencies features (https://universaldependencies.org/u/feat/) -> (en, fr, ro).
_PERSON = {
    ("1", "Sing"): ("I", "je", "eu"),
    ("2", "Sing"): ("you", "tu", "tu"),
    ("3", "Sing"): ("he/she", "il/elle", "el/ea"),
    ("1", "Plur"): ("we", "nous", "noi"),
    ("2", "Plur"): ("you (plural or polite)", "vous", "voi"),
    ("3", "Plur"): ("they", "ils/elles", "ei/ele"),
}
_TENSE = {
    ("Ind", "Pres"): ("present", "présent", "prezent"),
    ("Ind", "Past"): ("past", "passé", "trecut"),
    ("Ind", "Imp"): ("imperfect", "imparfait", "imperfect"),
    ("Ind", "Fut"): ("future", "futur", "viitor"),
    ("Sub", "Pres"): ("subjunctive", "subjonctif", "conjunctiv"),
    ("Cnd", None): ("conditional", "conditionnel", "condițional"),
    ("Imp", None): ("imperative", "impératif", "imperativ"),
}
_VERB_FORM = {
    "Part": ("past participle", "participe passé", "participiu"),
    "Ger": ("-ing form", "gérondif", "gerunziu"),
    "Inf": ("infinitive", "infinitif", "infinitiv"),
}
_PLURAL = ("plural", "pluriel", "plural")
_FEMININE = ("feminine", "féminin", "feminin")
_DEFINITE = ("definite article", "article défini", "articulat hotărât")
_GEN_DAT = ("genitive-dative", "génitif-datif", "genitiv-dativ")
_DEFINITE_SHORT = ("definite", "défini", "articulat")


def parse_feats(feats: str | None) -> dict[str, str]:
    """"Case=Gen|Definite=Def" -> {"Case": "Gen", "Definite": "Def"}."""
    if not feats:
        return {}
    return dict(part.split("=", 1) for part in feats.split("|") if "=" in part)


def form_note(form: str, base_form: str, upos: str, feats: str | None) -> dict[str, str] | None:
    """The note shown on the word sheet for this form, or None when the form needs none (it is the
    base form, or its features say nothing worth showing)."""
    if form.lower() == base_form.lower().removeprefix("a "):
        return None
    f = parse_feats(feats)
    parts = []
    if upos in ("VERB", "AUX"):
        if f.get("VerbForm") in _VERB_FORM:
            parts.append(_VERB_FORM[f["VerbForm"]])
        else:
            tense = _TENSE.get((f.get("Mood"), f.get("Tense"))) or _TENSE.get((f.get("Mood"), None))
            person = _PERSON.get((f.get("Person"), f.get("Number")))
            if tense and person:
                parts.append(tuple(f"{t}, {p}" for t, p in zip(tense, person)))
            elif tense:
                parts.append(tense)
    else:
        if f.get("Case") in ("Gen", "Dat", "Dat,Gen") and f.get("Definite") == "Def":
            parts.append(tuple(f"{c}, {d}" for c, d in zip(_GEN_DAT, _DEFINITE_SHORT)))
        if f.get("Number") == "Plur":
            parts.append(_PLURAL)
        if f.get("Definite") == "Def" and f.get("Case") not in ("Gen", "Dat", "Dat,Gen") and upos == "NOUN":
            parts.append(_DEFINITE)
        if f.get("Gender") == "Fem" and upos == "ADJ":
            parts.append(_FEMININE)
    if not parts:
        return None
    en, fr, ro = (", ".join(p[i] for p in parts) for i in range(3))
    return {"en": en, "fr": fr, "ro": ro}
