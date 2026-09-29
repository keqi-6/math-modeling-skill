# Provenance and delivery quality

Read this rule for every substantive task.

## Evidence chain

Maintain both directions:

```text
input → interpretation → treatment/design → specification → code → frozen output → verification →
figure/table/prose → conclusion

claim → figure/table/frozen output → code → specification → interpretation → original input
```

For every material artifact record producer, inputs, parameters or decision identity, timestamp or
version, dimensions, units, hash where appropriate, and consumers.

## Authority

- Original statements and inputs are immutable evidence.
- Current approved interpretations and specifications have one owner each.
- Frozen outputs are not authoritative beyond their producer and verification identity.
- Handoffs, state files, READMEs, and logs are navigation aids, not completion proof.
- Archives and excellent papers preserve provenance or expression examples; they do not become
  current truth or model authority.

## Change propagation

When an upstream layer changes, identify every direct and transitive consumer. Regenerate it, prove
it remains valid, or mark it provisional/invalid. Synchronization is demonstrated by content and
identity checks, not by a copy command.

## Draft and formal delivery

- Keep drafts isolated and visibly marked in filename plus page or metadata.
- Do not occupy the formal entry point before explicit promotion.
- Do not promote until all required components are verified, evaluator-visible chains are complete,
  rendered pages are inspected, and the user explicitly approves formal status.
- Package only current, traceable, necessary files and verify the package itself.

