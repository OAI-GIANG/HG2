# HG (clean-slate)

Independent HG product: new repository, parentless genesis, fresh implementation.
Roles: PHONE = single primary runtime and state owner; VPS1 = HTTPS edge relay (never the
primary runtime, never holds the model key); VPS2 = standby/worker only.
No fork, no inherited history, no reused runtime/authority/state engine, standard library only.
