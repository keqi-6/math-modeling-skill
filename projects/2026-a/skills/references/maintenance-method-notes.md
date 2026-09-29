# Skill 维护能力路由（非规范性）

本路由只在用户已经明确授权 `skill_maintenance` 后使用；它不产生授权，也不把普通项目请求升级为 Skill 修改。

## audit-and-change

审计、规则文本迁移、能力重组、定向修复或候选发布时，完整读取 [skill-maintenance.md](capability-packets/governance/skill-maintenance.md)。先把“规则语义、触发与适用性、控制器实现、方法表达、测试证据”分开，再选择真正受影响的层。

## 完整性边界

原子规则和机器契约仍是规范 owner；本能力包只说明如何审计、迁移与验证。历史账本用于找回语义和反例，不是运行时常驻上下文。候选版必须隔离于基线，最终冻结与安装仍需用户单独明确批准。
