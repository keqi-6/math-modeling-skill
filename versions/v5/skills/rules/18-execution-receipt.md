# 01 — 执行回执

## R-01 目的

回执是任务路由、规则触发和完成证据，不是工作总结。每个实质任务必须先建立开始回执，
结束前补齐结束回执。可以写入当前计划、审计、工作日志或临时结构化文件；不得只留在
模型的隐含推理中。

## R-02 开始回执

至少记录：

```yaml
task: 用户实际要求
task_type: 路由矩阵中的一个或多个类型
scope: 本轮允许检查或修改的对象
current_stage: 当前最早未关闭阶段
required_rules: 本轮必须完整读取的活动规则
required_inputs: 必须核验的事实来源
allowed_actions: 当前阶段与用户授权允许的动作
prohibited_actions: 本轮不得执行或不得升级的动作
full_read_gate: not_triggered | in_progress | closed
human_gate: not_triggered | awaiting | closed
```

开始回执必须由当前证据生成，不照抄旧回执。

## R-03 跳过证明

对路由后可能触发但未执行的条件规则逐项记录：

```yaml
skipped_rules:
  - rule_id: 稳定规则 ID
    trigger_checked: 具体触发条件
    evidence: 检查过的文件、事实或用户决定
    reason: 为什么本轮不触发
```

禁止只写“无关”“已处理”“不需要”“时间有限”。没有证据的跳过视为未执行。

## R-04 结束回执

至少记录：

```yaml
outputs: 新建或修改的真实产物
verification: 已实际执行的检查及结果
affected_downstream: 已同步、已失效或明确不受影响的消费者
unresolved: 尚未关闭的问题和风险
stage_closures: 本轮关闭的阶段及各自证据
completion_scope: local | stage | milestone | full_project
status: complete | partial | blocked
```

只有 `completion_scope` 与实际检查范围一致时才能宣布完成。局部修改、单脚本测试、
成功编译或单篇审读均不能写成 `full_project`。

## R-05 机械验证

Skill 维护和正式节点使用 `scripts/validate_skill_v3.py` 检查规则路由、稳定 ID、内部
引用和迁移台账，并运行 `scripts/test_skill_regressions.py` 检查已知失败模式仍被活动
规则覆盖。项目可另建回执验证器，但不得用“脚本通过”替代回执内容的真实性判断。
