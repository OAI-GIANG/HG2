# HG2 (clean-slate)

HG2 is the product/repository label. `PRODUCT_ID=HG` remains the durable event and on-disk identity; do not silently rename historical `product_id` values. This mapping does not imply compatibility with removed APIs or Bridge 1.1 capabilities.

Independent HG2 product: new repository, parentless genesis, fresh implementation.
Roles: PHONE = single primary runtime and state owner; VPS1 = HTTPS edge relay (never the
primary runtime, never holds the model key); VPS2 = standby/worker only.
No fork, no inherited history, no reused runtime/authority/state engine, standard library only.


Product-scope decisions and their blocked acceptance gates are recorded in `docs/PRODUCT_SCOPE_DECISIONS_HG2_V1.md`.
