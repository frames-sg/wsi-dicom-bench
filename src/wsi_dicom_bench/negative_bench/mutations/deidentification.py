"""One-field defects in a real encrypted synthetic Attribute container."""

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import finish
from .dicom import set_case_sop


def encrypted_attribute_edit(context: MutationContext) -> MutationResult:
    item = context.dataset.EncryptedAttributesSequence[0]
    if context.parameters.get("wrong_key_transport"):
        rsa = bytes.fromhex("06092a864886f70d010101")
        payload = bytes(item.EncryptedContent)
        if payload.count(rsa) != 1:
            raise GenerationError("encrypted control must contain one RSA key-transport identifier")
        item.EncryptedContent = payload.replace(rsa, bytes.fromhex("06092a864886f70d010107"), 1)
    if "transfer_syntax" in context.parameters:
        item.EncryptedContentTransferSyntaxUID = context.parameters["transfer_syntax"]
    set_case_sop(context.dataset, context.seed)
    context.changes.append({"kind": "encrypted_attribute_edit", "parameters": context.parameters})
    return finish(context)


HANDLERS = {"encrypted_attribute_edit": encrypted_attribute_edit}
