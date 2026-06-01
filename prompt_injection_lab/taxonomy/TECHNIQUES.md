# LivePI Technique Families

This file lists the canonical attack-technique or rendering-family space used by
the clean LivePI artifact. Machine-readable tags remain stable for code;
paper-facing names are used in tables and generated metadata.

| Tag | Paper-facing family name |
| --- | --- |
| `direct_group_message_instruction` | Direct group-message instruction |
| `checklist_handoff_injection` | Checklist handoff injection |
| `single_email_chain_spoofing` | Single-email chain spoofing |
| `trusted_integration_spoofing` | Trusted-integration spoofing |
| `compositional_instruction_attack` | Compositional instruction attack |
| `skill_rule_injection` | Skill-rule injection |
| `post_compaction_file_read_lure` | Post-compaction file-read lure |
| `approval_chain_spoofing` | Approval-chain spoofing |
| `covert_tool_binding` | Covert tool binding |
| `shadow_policy_update` | Shadow policy update |
| `state_desynchronization_override` | State-desynchronization override |
| `code_carried_execution` | Code-carried execution |

The ten prompt-level techniques are the middle ten rows. Direct group-message
instruction is a chat-surface rendering family, and code-carried execution is a
repository/package execution family.
