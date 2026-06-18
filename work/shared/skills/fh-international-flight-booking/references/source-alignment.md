# Source Alignment

> 加载时机：调试或更新 skill 时加载本文件。

## Java 后端路径映射

| 功能 | Java 类路径 |
|---|---|
| 国际航班查询 | `fh.travel.ai.busi.air.international.shopping.IntShoppingController` |
| 退改规则 | `fh.travel.ai.busi.air.international.rule.IntRuleController` |
| 核价 | `fh.travel.ai.busi.air.international.pricing.IntPricingController` |
| 差标校验 | `fh.travel.ai.busi.air.international.policy.IntPolicyController` |
| 出差单校验 | `fh.travel.ai.busi.air.international.application.IntCheckApplicationController` |
| 待下单数据 | `fh.travel.ai.busi.air.international.save.WaitSaveController` |
| 提交订单 | `fh.travel.ai.busi.air.international.save.SaveOrderController` |
| 签证提醒 | `fh.travel.ai.busi.air.international.visa.VisaController` |
| 客户基本数据 | `fh.travel.ai.busi.customer.ClientController` |
| 用户数据 | `fh.travel.ai.busi.customer.MineController` |
| 乘机人查询 | `fh.travel.ai.busi.customer.PassengerController` |
| 归属公司 | `fh.travel.ai.busi.customer.BelongCompanyController` |
| 项目组 | `fh.travel.ai.busi.customer.ProjectController` |
| 国籍代码 | `fh.travel.ai.busi.params.NationalityController` |
| 出差单列表 | `fh.travel.ai.busi.application.ApplicationController` |

## 更新规则

1. 后端接口变更时，先更新 `api-endpoint-map.md`，再同步 `schemas/api-contracts.json`
2. 新增 API 端点时，同步更新 SKILL.md 的 API Route Table
3. 返回字段变更时，同步更新 workflow 中的"返回关键字段提取"表
4. 枚举值变更时，同步更新 `api-endpoint-map.md` 的枚举速查
