# HG2 — Central Brain Intelligence, Evidence-Driven Governance & Controlled Evolution — Master Plan R2

- Ngày rà soát: 2026-10-19
- Repository duy nhất: OAI-GIANG/HG2
- Nhánh triển khai: stt/hg2-brain-orchestrator-r1-20261019
- Base của PR #29: hg-genesis, commit 1dca305b4d6e9442e259442486efb5127cc0cb09
- Candidate đầu kỳ: 67afde1ca027b4012ce0dde190dda00918da3aff, tree 28d042fb4c14f9d0f43a96841021403f702170b5
- Phân loại: DESIGN + LOCAL TEST CANDIDATE; không phải chứng nhận production
- Trạng thái sản phẩm: API-to-brain local E2E đã có bằng chứng với gateway giả; ba miền logic chưa có adapter hoạt động; workflow bền vững chưa gắn vào Brain; live provider và runtime đã triển khai chưa được xác minh.

## 1. MTC-1.0 — Master Task Controller

### OBJECTIVE
Thẩm định, thiết kế và từng bước hoàn thiện một đầu não logic duy nhất để tiếp nhận yêu cầu, phân loại ý định, lập kế hoạch, điều phối năng lực, thực thi có giới hạn, xác minh độc lập, quản trị cấu trúc và tiến hóa có kiểm soát.

### SCOPE
- Chỉ OAI-GIANG/HG2; không dùng repository khác làm đích thực thi.
- Năm miền là miền năng lực logic trực thuộc Central Brain, không phải năm đầu não hay năm quyền chỉ huy.
- Giai đoạn kiểm kê ban đầu là READ-ONLY. Thay đổi chỉ được thực hiện sau khi đã có baseline, finding, root cause, test plan và đường lui.
- Không biến tên module, nhánh Git, fixture, test double hay cấu hình thành bằng chứng về năng lực đang vận hành.
- Không thêm dịch vụ, thư viện ngoài hoặc phụ thuộc có phí khi chưa chứng minh được giá trị và khả năng vận hành trên Termux ARM64.

### INPUT
Master Plan R1; mã nguồn, manifest, cấu hình, test, lịch sử Git và bằng chứng của HG2; tiêu chí HNI hiện hành khi có liên quan; tài liệu kỹ thuật ngoài có nguồn và ngày kiểm tra rõ ràng.

### OUTPUT
1. Independent Critique Report.
2. Repository Architecture Map và Capability Inventory.
3. Dependency, Duplication, Authority Conflict Matrix.
4. Target Architecture và các hợp đồng phiên bản hóa.
5. Component Disposition Matrix.
6. Acceptance, Regression, Adversarial và Recovery Test Matrix.
7. Migration, Checkpoint, Rollback Plan.
8. Minimum Viable End-to-End Brain plan và bằng chứng.
9. External Research & Evidence Matrix.
10. Evolution Ledger và Readiness Report.

### ACCEPTANCE CRITERIA
- Mọi nhận định trọng yếu liên kết đến commit, file, dòng, lệnh và kết quả; chưa đủ bằng chứng thì UNKNOWN.
- Mỗi capability có owner logic duy nhất, schema, quyền được phép, side-effect class và điều kiện xác minh.
- Không có hai nguồn sự thật cho trạng thái nhiệm vụ hay hai đường bypass authorization.
- Không xóa hoặc thay thế thành phần trước khi lập bản đồ phụ thuộc và kiểm thử tương thích.
- Có positive, negative, adversarial, failure-injection, restart-recovery và rollback tests.
- Đo chất lượng đầu ra, an toàn, quy trình, thời gian, chi phí và tài nguyên; không bịa ngưỡng trước baseline.
- Tách bạch PROPOSED, IMPLEMENTED, TESTED, VERIFIED, OPERATIONAL, BLOCKED và UNKNOWN.

### EVIDENCE
Mỗi hồ sơ bằng chứng phải chứa ID, thời điểm, device/runtime, commit/tree, trạng thái worktree, phạm vi, lệnh, exit code, log digest, test inventory, giới hạn và kết luận được phép rút ra. SHA-256 chỉ chứng minh tính nhất quán byte và liên kết nội bộ, không chứng minh danh tính tác giả, quyền hạn hay runtime từ xa.

### RISKS
Sai phân loại; prompt injection; capability overreach; kết quả giả; trạng thái mất sau crash; retry gây tác dụng phụ kép; tri thức lỗi thời; nguồn sự thật kép; tài nguyên/chi phí không giới hạn; test fixture không đại diện runtime; rollback không khả thi.

### STOP CONDITION
Dừng khi sai repository/branch, trạng thái chuẩn không rõ, thiếu quyền, worktree có thay đổi không được nhận diện, dữ liệu có nguy cơ mất, integrity check thất bại, evidence verifier không đáng tin, khả năng rollback chưa xác minh, hoặc hành động vượt quyền.

### NEXT ACTION
Tiếp tục đóng cổng P0 theo finding đã xác định; giữ PR #29 ở Draft cho đến khi các khoảng trống về state durability, trusted registry, verifier và runtime acceptance được xử lý.

## 2. Executive decision

R2 giữ nguyên hướng thiết kế một Central Brain nhưng hạ mọi tuyên bố xuống mức bằng chứng. Orchestrator hiện tại là một lõi điều phối đồng bộ, theo capability allowlist và fail-closed. Nó chưa phải một hệ lập kế hoạch tự chủ đầy đủ và chưa phải workflow engine bền vững.

Đề xuất:
- KEEP: một logical command brain; hợp đồng yêu cầu/kết quả; capability gate; trạng thái PARTIAL/IN_DOUBT; một canonical phone-owned state authority.
- IMPROVE: ghi audit trước external call; bind execution vào task/workflow ledger; kiểm chứng capability registry từ nguồn tin cậy; thêm test đối kháng và phép đo.
- INVESTIGATE: cách kết nối WorkflowService/DurableTransactionStore với StateStore hiện hữu mà không tạo database hoặc history thứ hai.
- DEFER: song song hóa nhiều nhánh, dynamic self-modification, autonomous delete/merge/deploy, service hóa từng trách nhiệm.
- BLOCK: gọi bất kỳ miền nào là OPERATIONAL nếu mới có registry entry, synthetic adapter hoặc unit test.

## 3. Bằng chứng baseline thực tế

### Kiểm kê môi trường
- Device: localhost qua Remote Desktop Commander; hệ điều hành báo Linux Android 15, kiến trúc aarch64.
- Checkout sử dụng: /data/data/com.termux/files/home/HG2-CONSOLIDATION.
- Branch: stt/hg2-brain-orchestrator-r1-20261019.
- HEAD: 67afde1ca027b4012ce0dde190dda00918da3aff.
- Tree: 28d042fb4c14f9d0f43a96841021403f702170b5.
- Remote ref được đọc bằng git ls-remote trùng HEAD tại thời điểm kiểm tra; base hg-genesis là 1dca305b4d6e9442e259442486efb5127cc0cb09.
- Worktree tại checkout này sạch trước thay đổi; không có diff staged/unstaged.
- Một checkout khác tại ~/HG2 đang nằm trên nhánh voice-tools, behind 17 và có untracked files. Nó không được sử dụng hoặc sửa trong công việc này.
- Baseline: 240 unittest PASS với ResourceWarning được nâng thành error; log SHA-256 32de458237595c9f8e5b50b1fad1bbccf792290ad88aaec13b149a3f3e92a6b2. Thời gian test ghi trong log: 21.429 giây.

### Mức độ bằng chứng
- IMPLEMENTED: hg/brain_orchestrator.py, hg/contracts.py, POST /api/ask gọi BrainOrchestrator.
- TESTED: test_brain_orchestrator, test_server và test suite baseline trên Termux.
- PARTIALLY VERIFIED: local HTTP route với PhoneRuntime/state thật ở môi trường test và deterministic fake gateway; kết quả provider được đánh dấu RESPONSE_ONLY, tổng thể PARTIAL.
- NOT VERIFIED: live model-provider, deployed phone service, ba miền logic còn thiếu adapter, durable orchestration/restart replay, authority của một registry runtime tin cậy, đánh giá chất lượng đầu ra trên corpus đại diện.
- Không có cơ sở để tuyên bố production, release hoặc tất cả năm miền đang hoạt động.

## 4. Kiến trúc đích

A. Intake & Context: xác thực envelope, giới hạn kích thước, danh tính người yêu cầu, nguồn và độ tin cậy; tách dữ liệu tham khảo khỏi chỉ thị; phát hiện thiếu thông tin và trả câu hỏi làm rõ khi cần.

B. Central Planner: đề xuất loại công việc, DAG phụ thuộc, thứ tự, song song hóa, risk tier, ngân sách, deadline, idempotency và điều kiện dừng. Kết quả của LLM là proposal không có quyền; validator xác định plan được chấp nhận.

C. Capability Registry & Router: registry có schema/phiên bản, owner duy nhất, adapter binding, quyền, side effects, timeout, resource budgets, evidence contract, retry semantics, runtime health và trạng thái xác minh. Không route theo tên gọi hoặc lời tự khai của worker.

D. Workflow State Manager: quản lý task ID, idempotency key, plan digest, version, checkpoint, attempt, deadline, trạng thái từng step, outcome và phục hồi. Trạng thái nhiệm vụ phải ở canonical state owner; không thêm store thứ hai.

E. Execution Layer: adapters hẹp, quyền tối thiểu, đầu vào đã chuẩn hóa, timeout ở adapter, idempotency, ghi audit trước side effect; không cho model gọi shell/tool trực tiếp.

F. Independent Verification: thực thi kiểm tra độc lập với adapter tạo ra kết quả; xác minh digest, nguồn, revision, schema, quyền và tiêu chí đầu ra. Lời tự xác nhận từ worker không đủ.

G. Architecture Governance: inventory tracked/untracked, manifest, dependency graph, ownership, test mapping, duplicate/conflict detection; xóa/chuyển đổi chỉ sau disposition decision và migration/rollback.

H. Knowledge & Evolution: provenance, source date, scope, confidence, contradictions, expiry/revalidation policy; lưu quyết định được nhận và bị bác bỏ; cải tiến qua test fixture cố định và review.

I. Cross-Cutting Controls: authorization, policy veto, append-only audit, trace/correlation, resource controls, checkpoints, rollback, release gates và kill switch.

Đây là ranh giới trách nhiệm logic, không phải yêu cầu tạo chín process hay agent riêng biệt. Chỉ tách module/service nếu phép đo chứng minh lợi ích lớn hơn chi phí vận hành.

## 5. Chuỗi điều khiển chuẩn

1. Authenticate caller và kiểm tra scope tại API.
2. Chuẩn hóa request; tính digest; gắn request ID, correlation ID, source manifest và idempotency key.
3. Phân loại task và rủi ro; chỉ chấp nhận capability thuộc allowlist.
4. Sinh DAG; validator loại dependency vòng, bước thiếu owner và quyền vượt mức.
5. Capability Registry xác nhận adapter đang được bind và health/contract có hiệu lực.
6. Policy Gate cấp quyền cho đúng task/action; high-risk actions yêu cầu approval độc lập.
7. Ghi task/plan/checkpoint vào canonical state trước side effect.
8. Thực thi theo thứ tự phụ thuộc; giới hạn step, deadline, retry, RAM/CPU/network/cost.
9. Ghi start event trước mỗi provider/tool call. Nếu ghi thất bại, không gọi external system.
10. Ghi kết quả và evidence; nếu outcome không rõ sau side effect, chuyển IN_DOUBT, không retry mù.
11. Independent verifier kiểm tra; aggregate không đoán kết quả thắng.
12. Persist terminal status; trả kết quả cùng evidence/status và giới hạn; cập nhật Evolution Ledger nếu có quyết định kiến trúc.

## 6. Năm miền logic

| Miền | Trách nhiệm | Quyền giới hạn | Trạng thái hiện tại |
|---|---|---|---|
| memory_knowledge | Truy vấn, hồi tưởng, provenance, freshness, conflict candidate | Đọc theo scope; chỉ ghi qua API được cấp quyền | Có adapter memory cho /api/ask; chưa đủ chứng minh toàn bộ miền operational |
| research_synthesis | Phân tích nguồn, tổng hợp, nêu luận cứ/độ bất định | Không tự thực thi kết luận; nguồn ngoài là dữ liệu không tin cậy | Adapter model-answer hiện trả RESPONSE_ONLY, không phải xác minh nghiên cứu độc lập |
| planning_coordination | Decompose, dependency DAG, scheduling, workflow state | Không cấp quyền; plan phải qua validator và policy gate | Chưa có operational adapter trên /api/ask |
| tools_execution | Hẹp hóa tool adapters, thực thi, artifact, result receipts | Mặc định deny; side effects phân loại; không shell quyền tự do | Chưa có operational adapter được route trên /api/ask |
| security_verification | Policy check, evidence validation, conflict review | Quyền phủ quyết; không phê chuẩn bằng lời tự khai của executor | Validator/evidence callback hiện hữu nhưng chưa là verifier độc lập production |

“Miền” không đồng nghĩa Git branch, process độc lập, model độc lập hoặc quyền hạn ngang hàng.

## 7. Quy tắc về quyền và tác dụng phụ

- Registry chỉ khai báo khả năng; policy engine mới quyết định action được phép cho principal, task, resource và thời điểm cụ thể.
- Không cho capability của một miền tự mở rộng capability của miền khác.
- LLM/classifier có thể đề xuất, không thể mint principal, approval, credential hay capability.
- READ_ONLY, LOCAL_WRITE, EXTERNAL_WRITE, DESTRUCTIVE, MERGE/RELEASE/DEPLOY là các side-effect tiers đề xuất; danh sách cuối phải map đến policy code.
- Mọi external write, delete, merge, deploy cần scope chính xác và evidence gate; thao tác không thể rollback phải có compensation/containment plan trước khi bắt đầu.
- Prompt injection từ user, web, file, memory hoặc model result phải được xử lý như dữ liệu không tin cậy; không bao giờ là nguồn policy.
- Timeout không đồng nghĩa thao tác thất bại. Sau timeout khi side effect có thể đã xảy ra, trạng thái là IN_DOUBT cho đến khi reconcile.
- Retry chỉ cho thao tác được xác định idempotent; key phải ổn định qua retry và gắn payload digest.
- Cấm log prompt, response, credential, tool arguments hoặc outputs đầy đủ; log digest, loại thao tác, policy decision, evidence ref và status.

## 8. Trạng thái và hợp đồng kết quả

- PROPOSED: ý tưởng chưa có mã.
- IMPLEMENTED: mã/cấu hình tồn tại.
- TESTED: test đã chạy với commit/runtime/exit code/log digest.
- VERIFIED: test và evidence đáp ứng một tiêu chí xác định.
- OPERATIONAL: hoạt động quan sát được trong môi trường được nêu.
- BLOCKED: không được tiếp tục, nêu lý do.
- UNKNOWN: chưa đủ bằng chứng.
- SUCCESS chỉ khi tất cả bước bắt buộc đủ kết quả và independent verifier trả pass.
- RESPONSE_ONLY là câu trả lời được sinh ra; không chứng minh hành động bên ngoài hay correctness.
- PARTIAL không được nâng thành SUCCESS chỉ vì có câu trả lời.
- IN_DOUBT yêu cầu reconciliation; không tự retry tác dụng phụ không idempotent.
- BLOCKED, FAIL, PARTIAL, INCONCLUSIVE và IN_DOUBT phải giữ riêng khi hiển thị và đo lường.

## 9. Ma trận metric

Baseline và test corpus phải được thiết lập trước khi chốt ngưỡng số học. Bắt buộc đo:
- Intent classification accuracy, abstain/clarification precision, capability routing precision/recall trên bộ oracle đóng băng.
- End-to-end goal completion và result acceptance theo rubric độc lập.
- Unauthorized action count trên suite đối kháng; mục tiêu 0 cho bộ test đã định nghĩa.
- Evidence completeness, evidence verifier false-accept/false-reject trên fixture chuẩn.
- Mean/p95 latency, retries/task, tool calls/task, bytes, peak RSS, CPU time, battery/thermal khi có khả năng đo.
- Duplicated side effects, idempotency collisions, IN_DOUBT recovery rate, crash recovery and rollback success.
- Regression failures, prompt injection success rate, stale knowledge detection, unbounded-consumption/cost-limit blocks.
Không dùng một scalar score để bù đắp lỗi quyền hạn, mất dữ liệu hoặc verifier false-accept.

## 10. Lộ trình và cổng

### Phase 0 — Independent Adversarial Review
Kết quả: critique và research matrix. Gate: mỗi finding nghiêm trọng có phản biện, bằng chứng, failure scenario và alternative.

### Phase 1 — Read-Only Audit
Đã thực hiện trên checkout chỉ định. Gate: branch/base/status/worktree và baseline test được ghi lại. Checkout voice-tools và các checkout khác không sửa.

### Phase 2 — Failure & Conflict Analysis
Kết quả: các finding F-01…F-10 và risk matrix. Gate: nguyên nhân gốc được liên kết source; không chỉ mô tả triệu chứng.

### Phase 3 — Target Contracts
Định nghĩa trong tài liệu capability contracts. Gate: input/output, invariants, authority, error states, idempotency, timeout, evidence và verification rõ ràng.

### Phase 4 — Component Disposition
Định nghĩa trong disposition matrix. Gate: không có DELETE trong đợt này; các vùng trùng lặp hoặc state ownership không rõ được INVESTIGATE/QUARANTINE trước.

### Phase 5 — Acceptance & Adversarial Testing
Bổ sung test pre-call audit failure. Gate: focused tests, full suite, py_compile, manifest validation, diff check và evidence hashes đều PASS.

### Phase 6 — Minimum Viable End-to-End Brain
Luồng POST /api/ask → authorized memory → model adapter → typed aggregate đã có local HTTP test. Nó chứng minh wiring với fake gateway chứ không phải live-provider, chất lượng nội dung hay deployed runtime. Tổng trạng thái PARTIAL là đúng.

### Phase 7 — Controlled Implementation
Thay đổi nhỏ, checkpoint trước/sau, test hồi quy/đối kháng, hash manifest và rollback. Commit/push nhánh của PR #29 được phép khi test xanh; không merge hoặc deploy khi durable workflow, registry, verifier và runtime acceptance chưa đạt.

### Phase 8 — Continuous Evolution
Chỉ cải tiến theo metric đã đo; lưu decision ledger; không tự xóa hoặc tự cấp thêm quyền theo chỉ số chất lượng.

## 11. Điều kiện đóng R2

Đóng gói thiết kế R2 và remediation candidate không đồng nghĩa đóng sản phẩm. Đóng thiết kế khi:
- kiến trúc, critique, contracts, disposition và test matrix nhất quán;
- finding P0 trong phạm vi đợt này đã sửa và có test âm;
- full suite và evidence reproducible;
- PR có mô tả giới hạn trung thực.

Chỉ đóng release gate/merge khi có thêm: workflow durable được dùng chung state authority và được test restart; registry từ nguồn tin cậy; verifier độc lập; adapter cho capability cần thiết; live-provider và deployed-phone evidence; external review/owner acceptance; rollback/restore proof.

## 12. Deliverables

1. External research & evidence matrix: HG2-CENTRAL-BRAIN-EXTERNAL-RESEARCH-R2.md.
2. Independent critique report: HG2-CENTRAL-BRAIN-INDEPENDENT-CRITIQUE-R2.md.
3. Repository architecture map: HG2-CENTRAL-BRAIN-REPOSITORY-ARCHITECTURE-MAP-R2.md.
4. Capability inventory: HG2-CENTRAL-BRAIN-CAPABILITY-INVENTORY-R2.md.
5. Dependency, duplication & conflict matrix: HG2-CENTRAL-BRAIN-DEPENDENCY-CONFLICT-MATRIX-R2.md.
6. Risk register & failure taxonomy: HG2-CENTRAL-BRAIN-RISK-REGISTER-R2.md.
7. Central Brain target contracts: HG2-CENTRAL-BRAIN-CAPABILITY-CONTRACTS-R2.md.
8. Component disposition matrix: HG2-CENTRAL-BRAIN-DISPOSITION-MATRIX-R2.md.
9. Acceptance/regression/adversarial test matrix: HG2-CENTRAL-BRAIN-FAILURE-TEST-MATRIX-R2.md plus tests/test_server.py and tests/test_brain_orchestrator.py.
10. Migration, checkpoint & rollback plan: HG2-CENTRAL-BRAIN-MIGRATION-CHECKPOINT-ROLLBACK-R2.md.
11. Minimum viable end-to-end plan: HG2-CENTRAL-BRAIN-MVE-END-TO-END-PLAN-R2.md.
12. Evolution ledger, evidence index & readiness report: HG2-CENTRAL-BRAIN-EVOLUTION-LEDGER-R2.md and evidence/HG2-CENTRAL-BRAIN-R2-AUDIT-20261019.json.

All items above describe the design/evidence package. They do not claim the five domains are operational or release gates are closed.

## 13. External references

- NIST AI RMF Playbook: https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-rmf-playbook
- NIST AI RMF Core: https://airc.nist.gov/airmf-resources/airmf/5-sec-core/
- NIST GenAI Profile NIST AI 600-1: https://www.nist.gov/itl/ai-risk-management-framework/ai-risk-management-framework-resources
- OWASP GenAI LLM Top 10 2026 (current release published 2026-08-04): https://genai.owasp.org/llm-top-10/ and source repository https://github.com/GenAI-Security-Project/GenAI-LLM-Top10
- Saga pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/saga
- Idempotent Consumer: https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer
- Transactional Outbox: https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos
- OpenTelemetry Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- Google code review guidance: https://google.github.io/eng-practices/review/
- Google SRE production testing: https://sre.google/sre-book/testing-reliability/

These sources supply design principles, not proof that HG2 has implemented them.
