"""Apply a precomputed, precisely authored MAC defect without retaining a key."""

import hashlib
import json
from pathlib import Path

from ..model import GenerationError, MutationContext, MutationResult
from ..signature_statement_cases import MUTATIONS_PATH
from .dicom import save


def signature_mac_defect(context: MutationContext) -> MutationResult:
    vectors = json.loads((Path(__file__).parents[1] / MUTATIONS_PATH).read_text())
    item = context.dataset.DigitalSignaturesSequence[0]
    signature = bytes(item.Signature)
    if signature.hex() != vectors["original_signature"]:
        raise GenerationError("signature mutations do not belong to this signed control")
    variant = context.parameters["variant"]
    if variant == "omit-declared-tag":
        parameters = context.dataset.MACParametersSequence[0]
        parameters.DataElementsSigned = [tag for tag in parameters.DataElementsSigned if int(tag) != 0x00080018]
    elif variant == "wrong-timestamp-imprint":
        # Locate the actual RFC3161 messageImprint, not an arbitrary byte.
        imprint = hashlib.sha256(signature).digest()
        token = bytes(item.CertifiedTimestamp)
        if token.count(imprint) != 1:
            raise GenerationError("timestamp control must contain one Signature message imprint")
        at = token.index(imprint)
        item.CertifiedTimestamp = token[:at] + bytes([token[at] ^ 1]) + token[at + 1:]
    else:
        if variant not in vectors["signatures"]:
            raise GenerationError(f"unknown MAC defect {variant}")
        item.Signature = bytes.fromhex(vectors["signatures"][variant])
    # The signed SOP UID must remain unchanged: changing it would create a
    # second signature defect unrelated to the named MAC encoding rule.
    save(context.dataset, context.default_output)
    return MutationResult([context.default_output], [{"kind": "authored_mac_defect", "variant": variant}])


HANDLERS = {"signature_mac_defect": signature_mac_defect}
