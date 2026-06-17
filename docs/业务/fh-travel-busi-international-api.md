---
title: fh-travel-busi
language_tabs:
  - shell: Shell
  - http: HTTP
  - javascript: JavaScript
  - ruby: Ruby
  - python: Python
  - php: PHP
  - java: Java
  - go: Go
toc_footers: []
includes: []
search: true
code_clipboard: true
highlight_theme: darkula
headingLevel: 2
generator: "@tarslib/widdershins v4.0.30"

---

# fh-travel-busi

Base URLs:

# Authentication

# 国际机票/国际机票SKILL

## POST 航班查询

POST /air/international/intShopping

> Body 请求参数

```json
{
  "stopQuantity": 0,
  "onlyBigCustomerPrice": true,
  "clientId": "string",
  "language": "en,",
  "airIdList": [
    "string"
  ],
  "passengerType": "string",
  "cabClass": [
    "FIRST"
  ],
  "tripList": [
    {
      "fromCity": "string",
      "toCity": "string",
      "flyDate": "string",
      "isCity": true
    }
  ],
  "preferences": {
    "transport": [
      "string"
    ],
    "allianceCode": "string",
    "changeable": true,
    "refundable": true,
    "upgradable": true,
    "freeBaggageOnly": true
  }
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» stopQuantity|body|integer| 是 ||经停次数: 0直飞 1经停一次 2经停二次|
|» onlyBigCustomerPrice|body|boolean| 是 ||仅查大客户价|
|» clientId|body|string| 否 ||企业客户ID (指定客户ID)|
|» language|body|string| 是 ||none|
|» airIdList|body|[string]| 否 ||航司|
|» passengerType|body|string| 是 ||ADT(成本)，CHD(儿童)，INF(婴儿)|
|» cabClass|body|[string]| 否 ||舱位等级|
|» tripList|body|[object]| 是 ||none|
|»» fromCity|body|string| 是 ||出发地点|
|»» toCity|body|string| 是 ||到达地点|
|»» flyDate|body|string| 是 ||起飞日期：yyyy-MM-dd|
|»» isCity|body|boolean| 是 ||是否城市码|
|» preferences|body|object| 否 ||旅客偏好|
|»» transport|body|[string]| 否 ||none|
|»» allianceCode|body|string| 否 ||联盟代码,   OW: One World(寰宇一家);   SA: StarAlliance(星空联盟);   ST: SkyTeam（天合联盟）|
|»» changeable|body|boolean| 否 ||是否允许变更|
|»» refundable|body|boolean| 否 ||是否允许退票|
|»» upgradable|body|boolean| 否 ||是否允许升舱|
|»» freeBaggageOnly|body|boolean| 否 ||仅返回有免费行李的运价|

#### 枚举值

|属性|值|
|---|---|
|» language|en,|
|» language|cn|
|» cabClass|FIRST|
|» cabClass|PREMIUM_FIRST|
|» cabClass|BUSINESS|
|» cabClass|PREMIUM_BUSINESS|
|» cabClass|ECONOMY|
|» cabClass|PREMIUM_ECONOMY|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "serialNumber": "string",
    "groupList": [
      {
        "groupId": "string",
        "tripList": [
          {
            "id": null,
            "airLine": null,
            "duration": null,
            "mile": null,
            "virtualInd": null,
            "flightList": null,
            "visaInfoList": null
          }
        ],
        "priceList": [
          {
            "priceId": null,
            "airId": null,
            "officeId": null,
            "supplier": null,
            "source": null,
            "price": null,
            "tax": null,
            "addPrice": null,
            "servicePrice": null,
            "totalPrice": null,
            "customersId": null,
            "passengerType": null,
            "allowTicket": null,
            "specialRate": null,
            "selfBigCustomersId": null,
            "ruleList": null,
            "tripList": null
          }
        ]
      }
    ],
    "baggageList": [
      {
        "id": 0,
        "baggageType": "string",
        "pieces": 0,
        "weight": 0,
        "totalWeight": 0,
        "sizeText": "string",
        "textEn": "string",
        "textCh": "string"
      }
    ],
    "flightAttributeMap": [
      {
        "id": "string",
        "cabClassList": [
          {
            "cabClass": null,
            "wifi": null,
            "power": null,
            "seat": null
          }
        ]
      }
    ],
    "cityList": [
      {
        "cityCode": "string",
        "cityName": "string",
        "airPortName": "string"
      }
    ],
    "airwayList": [
      {
        "companyNo": "string",
        "companyName": "string",
        "fullCompanyName": "string",
        "pertainName": "string"
      }
    ],
    "typeList": [
      {
        "type": "string",
        "airCom": "string",
        "size": "string",
        "name": "string"
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||返回标识，0：成功，其他，错误|
|» errorMsg|string|false|none||错误信息|
|» requestSeqNo|string|false|none||请求序列号|
|» data|object|false|none||none|
|»» serialNumber|string|false|none||缓存key|
|»» groupList|[object]|true|none||航班集合|
|»»» groupId|string|true|none||航班序号|
|»»» tripList|[object]|true|none||行程列表: 去程,回程|
|»»»» id|string|true|none||序号|
|»»»» airLine|string|true|none||航程（起始-终点|
|»»»» duration|integer|false|none||飞行时长，格式：分钟|
|»»»» mile|integer|false|none||里程|
|»»»» virtualInd|boolean|false|none||拼接标识: 虚拟组合|
|»»»» flightList|[object]|true|none||航段|
|»»»»» id|integer|true|none||序号|
|»»»»» uniqueId|integer|true|none||唯一ID, 不同组相同航班, 此ID相同, 可以通过此ID获取航班基础设施|
|»»»»» flightId|string|true|none||航班号|
|»»»»» operatingFlightId|string|true|none||承运航班号|
|»»»»» airLine|string|true|none||航段|
|»»»»» flyDate|string|true|none||起飞时间|
|»»»»» arrDate|string|true|none||到达时间|
|»»»»» duration|integer|true|none||飞行时长，格式：分钟|
|»»»»» mile|integer|true|none||里程|
|»»»»» meal|string|true|none||常见餐食代码如下： B 早餐 C 免费酒精饮料 D 正餐 F 供采购的食物 G 供采购的食物和饮料 H 热的膳食 K 轻快早餐 L 午餐 M 膳食 N 没有饭食供应 O 冷的膳食 P 供采购的酒精饮料 R 茶点 S 快餐 V 供采购的茶点|
|»»»»» type|string|true|none||机型|
|»»»»» typeGroup|string|true|none||机型分组代码|
|»»»»» fromPort|string|true|none||起飞航站楼|
|»»»»» toPort|string|true|none||到达航站楼|
|»»»»» et|boolean|true|none||电子客票|
|»»»»» asr|boolean|true|none||ASR 标识|
|»»»»» avls|string|true|none||所有舱位字符串|
|»»»»» stopList|[object]|true|none||经停点|
|»»»»»» stopPort|string|true|none||经停机场|
|»»»»»» stopTime|integer|true|none||经停时间|
|»»»» visaInfoList|[object]|false|none||签证信息|
|»»»»» visaType|string|false|none||签证类型，过境 TRANS/入境ENTRY|
|»»»»» isVisaNeeded|boolean|false|none||是否需要签证|
|»»»»» country|string|false|none||国家两字码|
|»»»»» airPort|string|false|none||机场三字码|
|»»»»» text|string|false|none||文本描述|
|»»» priceList|[object]|true|none||价格列表|
|»»»» priceId|string|true|none||价格唯一ID, 含组ID|
|»»»» airId|string|true|none||出票航司|
|»»»» officeId|string|true|none||出票Office|
|»»»» supplier|string|true|none||供应商类型:LCC|
|»»»» source|string|true|none||供应商来源|
|»»»» price|number|true|none||票价|
|»»»» tax|string|true|none||税费|
|»»»» addPrice|string|true|none||加价|
|»»»» servicePrice|string|true|none||服务费|
|»»»» totalPrice|string|true|none||总价|
|»»»» customersId|string|true|none||大客户号|
|»»»» passengerType|string|true|none||乘客类型|
|»»»» allowTicket|boolean|true|none||允许出票, 为false时,表示此价格只能帮客户代订|
|»»»» specialRate|integer|true|none||1 特殊运价|
|»»»» selfBigCustomersId|boolean|true|none||是否本司大客户号|
|»»»» ruleList|[object]|true|none||大客户规则说明|
|»»»»» officeId|string|false|none||公司officeId|
|»»»»» airCodes|string|true|none||航司代码";"号隔开 例:ZH;CA 非空|
|»»»»» bigCustomerId|integer|true|none||大客户号id--来自SBX_EnterpriseID的ID列 例:166|
|»»»»» priceType|string|true|none||运价类型 : 0:大客户价 1：白名单价 多个用“;”隔开,为空默认为全部 例:0;1|
|»»»»» beginContains|boolean|true|none||开始年龄是否包含生日当天|
|»»»»» beginAge|integer|true|none||开始年龄 0:不限制|
|»»»»» endContains|boolean|true|none||截止年龄是否包含生日当天|
|»»»»» endAge|integer|true|none||截止年龄 0:不限制|
|»»»»» allowNation|boolean|true|none||true:允许国籍/false：排除国籍|
|»»»»» nations|string|true|none||国籍二字码列表，以“;”号隔开 例:AF;AO;AI|
|»»»»» enterpriseId|string|true|none||大客户号 calc|
|»»»»» nationsCodeCn|string|true|none||国籍二字码中文列表，以“,”号隔开 例:阿富汗(AF),安哥拉(AO),安圭拉(AI) calc|
|»»»»» ruleDesc|string|true|none||大客户价格规则说明 calc|
|»»»»» sortPriority|integer|true|none||大客户价格规则优先级权重 calc 1.如果找到多条政策，优先设了大客户号的 2.如果没有找到，就返回其它所有政策（不用考虑优先级）|
|»»»» tripList|[object]|true|none||行程组合|
|»»»»» airLine|string|true|none||航线|
|»»»»» caption|string|true|none||价格名称,品牌名称: 航信NDC返回此栏位|
|»»»»» cabClass|string|true|none||舱位等级: Y-经济舱、W-高级经济舱、C-商务舱 、F-头等舱|
|»»»»» io|integer|true|none||0：去程,1:回程|
|»»»»» fareBasisCode|string|true|none||运价基础代码|
|»»»»» teamPrice|boolean|true|none||是否为小团队价|
|»»»»» ruleRef1|string|true|none||Fare rule key，用于查询规则时使用|
|»»»»» dataSource|string|true|none||数据来源|
|»»»»» rule|object|true|none||退改签规则|
|»»»»»» refund|boolean|true|none||允许退票|
|»»»»»» change|boolean|true|none||允许改期|
|»»»»»» upgra|boolean|true|none||允许升舱|
|»»»»»» refundRule|object|true|none||退票|
|»»»»»»» beforeDeparture|object|true|none||起飞前|
|»»»»»»»» allowed|boolean|true|none||是否允许|
|»»»»»»»» amount|integer|true|none||金额, -1表示没有发布规则,以航司为准|
|»»»»»»» afterDeparture|object|true|none||起飞后，如起飞前|
|»»»»»»» noshowBeforeDeparture|object|true|none||误机后全部未使用的，如起飞前|
|»»»»»»» noshowAfterDeparture|object|true|none||误机后部分使用的，如起飞前|
|»»»»»» changeRule|string|true|none||改签，如退票|
|»»»»»» noshowRule|string|true|none||误机，如退票|
|»»»»» cabList|[object]|true|none||价格的舱位组合|
|»»»»»» id|integer|true|none||序号|
|»»»»»» flightId|string|true|none||航班号|
|»»»»»» airLine|string|true|none||行程|
|»»»»»» cab|string|true|none||舱位|
|»»»»»» num|string|true|none||舱位数量|
|»»»»»» cabClass|string|true|none||舱位等级: Y-经济舱、W-高级经济舱、C-商务舱 、F-头等舱|
|»»»»»» carryBaggageId|string|true|none||手提行李ID;|
|»»»»»» checkBaggageId|string|true|none||托运行李ID;|
|»»»»» addServiceList|[object]|true|none||附加服务|
|»»»»»» serviceType|string|true|none||[“C”,“F”,“R”, ”T”,”M”,”Z”] C-行李相关 F-航班相关 R-规则相关，必须和票价组成 部分相关 T-票相关 M-商品 Z-只用于品牌运价内|
|»»»»»» serviceName|string|true|none||商业名称|
|»»»»»» tagTypeCn|string|true|none||标签中文|
|»» baggageList|[object]|true|none||行李规则|
|»»» id|integer|true|none||序号, 与在数组中的顺序一致|
|»»» baggageType|string|true|none||check:托运行李, carry:手提行李|
|»»» pieces|integer|true|none||行李件数|
|»»» weight|integer|true|none||行李单件重量,单位为公斤|
|»»» totalWeight|integer|true|none||行李总重,单位为公斤|
|»»» sizeText|string|false|none||尺寸说明|
|»»» textEn|string|false|none||行李英文说明|
|»»» textCh|string|false|none||行李英文说明|
|»» flightAttributeMap|[object]|true|none||航班属性列表|
|»»» id|string|false|none||序号|
|»»» cabClassList|[object]|false|none||舱位等级属性|
|»»»» cabClass|string|false|none||舱等|
|»»»» wifi|boolean|false|none||是否有wifi 所有FULL航班全部有wifi的才会标记true 整个飞机全部（Full）覆盖才会标记为true|
|»»»» power|boolean|false|none||是否有电源|
|»»»» seat|object|false|none||none|
|»»»»» pitch|integer|false|none||坐椅前后间距, 坐椅最前端与前面坐椅椅背的距离|
|»»»»» flatness|string|false|none||F: 完全倾斜 180 度平躺 A: 倾斜成一定角度 N: 不能完全平躺|
|»»»»» width|string|false|none||S： 标准 W： 更宽 为空表示暂无数据|
|»» cityList|[object]|true|none||none|
|»»» cityCode|string|true|none||城市三字码|
|»»» cityName|string|true|none||城市名称|
|»»» airPortName|string|true|none||机场名称|
|»» airwayList|[object]|true|none||航空公司集合|
|»»» companyNo|string|true|none||公司代号|
|»»» companyName|string|true|none||公司名称|
|»»» fullCompanyName|string|true|none||公司全称|
|»»» pertainName|string|true|none||航司联盟|
|»» typeList|[object]|true|none||机型列表|
|»»» type|string|false|none||机型|
|»»» airCom|string|false|none||航空公司|
|»»» size|string|false|none||尺寸|
|»»» name|string|false|none||名称|

## POST 退改规则查询

POST /air/international/intRule

> Body 请求参数

```json
{
  "serialNumber": "string",
  "priceId": "string",
  "pricingId": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» serialNumber|body|string| 是 ||缓存序列号|
|» priceId|body|string| 是 ||价格Id|
|» pricingId|body|string| 是 ||核价ID  对应核价的priceId|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": [
    {
      "airLine": "string",
      "io": 0,
      "refund": true,
      "change": true,
      "upgra": true,
      "changeRule": {
        "inAdvanceTime": 0,
        "inAdvanceUnit": "string",
        "beforeDeparture": {
          "allowed": true,
          "amount": "string"
        },
        "afterDeparture": {}
      },
      "refundRule": {},
      "cabList": [
        {
          "flightId": "string",
          "airLine": "string",
          "baggageList": [
            {}
          ]
        }
      ]
    }
  ]
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||标识，0：成功，其他：错误|
|» errorMsg|string|false|none||错误信息|
|» requestSeqNo|string|false|none||请求序号|
|» data|[object]|false|none||none|
|»» airLine|string|true|none||航线|
|»» io|integer|true|none||0：去程,1:回程|
|»» refund|boolean|true|none||允许退票|
|»» change|boolean|true|none||允许改期|
|»» upgra|boolean|true|none||允许升舱|
|»» changeRule|object|true|none||改期规则|
|»»» inAdvanceTime|integer|true|none||提前时间|
|»»» inAdvanceUnit|string|true|none||提前时间（单位）|
|»»» beforeDeparture|object|true|none||起飞前|
|»»»» allowed|boolean|true|none||是否允许|
|»»»» amount|string|true|none||起飞前金额, -1表示没有发布规则,以航司为准|
|»»» afterDeparture|object|true|none||起飞后，字段数据同起飞前|
|»» refundRule|object|true|none||退票规则，内容改期规则|
|»» cabList|[object]|true|none||舱位列表|
|»»» flightId|string|true|none||航班号|
|»»» airLine|string|true|none||行程|
|»»» baggageList|[object]|true|none||行李规则，如查询返回的行李规则|

## POST 下单前核价

POST /air/international/intPricing

> Body 请求参数

```json
{
  "language": "string",
  "clientId": "string",
  "flightList": [
    {
      "serialNumber": "string",
      "priceId": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» language|body|string| 是 ||语言   cn=中文   en=英文|
|» clientId|body|string| 是 ||指定客户ID|
|» flightList|body|[object]| 是 ||none|
|»» serialNumber|body|string| 是 ||缓存序列号|
|»» priceId|body|string| 是 ||价格ID|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": [
    {
      "source": "string",
      "serialKey": "string",
      "priceId": "string",
      "serialNumber": "string",
      "priceList": [
        {
          "priceId": "string",
          "passengerType": "ADT(\"ADT\", \"成人\", 0),",
          "oldPrice": 0,
          "oldTax": 0,
          "price": 0,
          "tax": 0,
          "totalPrice": 0,
          "servicePrice": 0,
          "addFee": 0,
          "flightList": [
            {}
          ]
        }
      ]
    }
  ]
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

*empty object*

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|true|none||none|
|» errorMsg|string|true|none||none|
|» requestSeqNo|string|true|none||none|
|» data|[object]|true|none||none|
|»» source|string|true|none||来源|
|»» serialKey|string|true|none||缓存key|
|»» priceId|string|true|none||价格ID|
|»» serialNumber|string|true|none||唯一序列号|
|»» priceList|[object]|true|none||价格组|
|»»» priceId|string|true|none||价格ID|
|»»» passengerType|string|true|none||乘客类型|
|»»» oldPrice|number|true|none||原票面价|
|»»» oldTax|number|true|none||原税费|
|»»» price|number|true|none||票面价|
|»»» tax|number|true|none||税费|
|»»» totalPrice|number|true|none||总价|
|»»» servicePrice|number|true|none||服务费|
|»»» addFee|number|true|none||加价|
|»»» flightList|[object]|true|none||航班列表|
|»»»» ref2|string|true|none||获取退改签信息标识|
|»»»» io|integer|true|none||0：去程,1:回程|
|»»»» flyDate|string|true|none||出发时间|
|»»»» arrDate|string|true|none||到达时间|
|»»»» flightId|string|true|none||航班ID|
|»»»» operatingFlightId|string|true|none||承运航班|
|»»»» airLine|string|true|none||航线|
|»»»» cab|string|true|none||舱位|
|»»»» num|string|true|none||舱位数量|
|»»»» cabClass|string|true|none||舱位等级: Y-经济舱、W-高级经济舱、C-商务舱 、F-头等舱|
|»»»» baggageList|[object]|true|none||行李规则|
|»»»»» id|integer|true|none||序号, 与在数组中的顺序一致|
|»»»»» baggageType|string|true|none||check:托运行李, carry:手提行李|
|»»»»» pieces|integer|true|none||行李件数|
|»»»»» weight|integer|true|none||行李单件重量,单位为公斤|
|»»»»» totalWeight|integer|true|none||行李总重,单位为公斤|
|»»»»» sizeText|string|true|none||尺寸说明|
|»»»»» textEn|string|true|none||行李英文说明|
|»»»»» textCh|string|true|none||行李中文说明|

#### 枚举值

|属性|值|
|---|---|
|passengerType|ADT("ADT", "成人", 0),|
|passengerType|CNN("CNN", "儿童", 1),|
|passengerType|CHD("CHD", "儿童", 1),|
|passengerType|INF("INF", "婴儿", 2),|
|passengerType|SEA("SEA", "海员", 3),|
|passengerType|STU("STU", "学生", 4),|
|passengerType|YTH("YTH", "青年旅客", 5),|
|passengerType|LBR("LBR", "劳工", 6),|
|passengerType|EMI("EMI", "移民旅客", 7),|
|passengerType|CMA("CMA", "有陪伴成人", 8),|
|passengerType|CMP("CMA", "陪伴人", 9);|

## POST 验证出差申请单

POST /air/international/intCheckApplication

> Body 请求参数

```json
{
  "flag": 0,
  "applicationId": 0,
  "flightList": [
    {
      "serialNumber": "string",
      "priceId": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» flag|body|integer| 是 ||0:管制,1:提醒|
|» applicationId|body|integer| 是 ||OA带过来的申请单|
|» flightList|body|[object]| 是 ||航班列表|
|»» serialNumber|body|string| 是 ||缓存序列号|
|»» priceId|body|string| 是 ||价格Id|

> 返回示例

> 200 Response

```json
{}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

## POST 违反国际机票差旅政策

POST /air/international/intPolicy

> Body 请求参数

```json
{
  "oaLogin": true,
  "flightList": [
    {
      "serialNumber": "string",
      "priceId": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» oaLogin|body|boolean| 是 ||是否oa跑转|
|» flightList|body|[object]| 是 ||none|
|»» serialNumber|body|string| 是 ||缓存Key|
|»» priceId|body|string| 是 ||价格Id|

> 返回示例

> 200 Response

```json
{}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

*empty object*

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|

## POST 获取归属公司

POST /air/customer/listClientBelongCompany

> Body 请求参数

```json
{
  "clientIdSpecify": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» clientIdSpecify|body|string| 是 ||指定客户 允许选客户名下单才能指定|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "dataList": [
      {
        "id": 0,
        "pid": 0,
        "name": "string",
        "bm": "string"
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» dataList|[object]|false|none||none|
|»»» id|number|true|none||none|
|»»» pid|number|true|none||none|
|»»» name|string|true|none||名字|
|»»» bm|string|true|none||公司编码|

## POST 获取项目组列表

POST /air/customer/getClientProject

> Body 请求参数

```json
{
  "clientIdSpecify": "string",
  "showAll": true
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» clientIdSpecify|body|string| 是 ||指定客户 允许选客户名下单才能指定|
|» showAll|body|boolean| 是 ||是否显示全部（包括已删除）|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "dataList": [
      {
        "id": 0,
        "pid": 0,
        "name": "string",
        "bm": "string",
        "del": true
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» dataList|[object]|false|none||none|
|»»» id|number|true|none||none|
|»»» pid|number|true|none||none|
|»»» name|string|true|none||名字|
|»»» bm|string|true|none||编码|
|»»» del|boolean|true|none||是否已删除|

## POST 国籍代码

POST /params/system/nationality

> Body 请求参数

```yaml
{}

```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": [
    {
      "names": "string",
      "nameCode": "string",
      "enames": "string"
    }
  ]
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|[object]|false|none||none|
|»» names|string|true|none||名称|
|»» nameCode|string|true|none||代号|
|»» enames|string|true|none||英文名|

## POST 获取待下单数据

POST /air/international/waitSave

> Body 请求参数

```json
{
  "applicationId": "string",
  "clientId": "string",
  "language": "string",
  "flightList": [
    {
      "serialNumber": "string",
      "priceId": "string",
      "pricingId": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» applicationId|body|string| 是 ||OA跳转的申请单ID|
|» clientId|body|string| 是 ||指定客户下单选择的企业客户ID|
|» language|body|string| 是 ||none|
|» flightList|body|[object]| 是 ||none|
|»» serialNumber|body|string| 是 ||序列号|
|»» priceId|body|string| 是 ||价格ID|
|»» pricingId|body|string| 是 ||核价ID   对应核价返回的priceId|

> 返回示例

> 200 Response

```json
{
  "errorMsg": "string",
  "errorCode": "string",
  "enErrorMsg": "string",
  "data": {
    "applicationIdOa": "string",
    "travelPolicyList": [
      {
        "id": 0,
        "describle": "string",
        "requireReason": true,
        "policyPermit": 0
      }
    ],
    "applicationList": [
      {
        "id": 0,
        "dh": "string",
        "match": 0,
        "travelReason": "string",
        "costCenterList": [
          {
            "id": null,
            "pid": null,
            "depId": null,
            "projectGroup": null,
            "discount": null,
            "budgetCode": null,
            "belongCompany": null,
            "belongCompanyCode": null,
            "belongProjectCode": null,
            "depName": null,
            "accountType": null,
            "costCode": null
          }
        ],
        "passengerList": [
          {
            "id": null,
            "pid": null,
            "userCode": null,
            "userName": null,
            "cardType": null,
            "cardId": null,
            "remark": null,
            "tel": null,
            "depName": null
          }
        ]
      }
    ],
    "mileageCardList": [
      {
        "code": "string",
        "airCode": "string",
        "airName": "string"
      }
    ],
    "insuranceList": [
      {
        "insuranceId": "string",
        "insurancePrice": "string",
        "insuranceName": "string",
        "insuranceDesc": "string"
      }
    ],
    "airLineList": [
      {
        "serialNumber": "string",
        "groupList": [
          {}
        ],
        "otherPriceList": [
          {
            "id": null,
            "tax": null,
            "price": null,
            "totalPrice": null,
            "serviceFee": null
          }
        ],
        "baggageList": [
          {
            "id": null,
            "baggageType": null,
            "pieces": null,
            "weight": null,
            "totalWeight": null,
            "textEn": null,
            "textCh": null,
            "sizeText": null
          }
        ],
        "flightAttributeMap": [
          {
            "uniqueId": null,
            "cabClassList": null,
            "field_140": null
          }
        ],
        "cityList": [
          {
            "airPortCode": null,
            "cityName": null,
            "airPortName": null,
            "countryName": null,
            "cityCode": null
          }
        ],
        "airwayList": [
          {
            "companyNo": null,
            "companyName": null,
            "fullCompanyName": null,
            "pertainName": null
          }
        ],
        "typeList": [
          {
            "type": null,
            "airCom": null,
            "size": null,
            "name": null
          }
        ]
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

*empty object*

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorMsg|string|true|none||none|
|» errorCode|string|true|none||none|
|» enErrorMsg|string|true|none||none|
|» data|object|true|none||none|
|»» applicationIdOa|string|true|none||OA跳转申请单 下单界面需默认此申请单|
|»» travelPolicyList|[object]|true|none||订单差旅政策|
|»»» id|integer|true|none||政策id|
|»»» describle|string|true|none||政策描述|
|»»» requireReason|boolean|true|none||是否必填原因|
|»»» policyPermit|integer|true|none||政策权限 1:免审批 2:需审批 3:现付下单 4:不能下单 来自权限  取此值 calc|
|»» applicationList|[object]|true|none||申请单数据|
|»»» id|integer|true|none||none|
|»»» dh|string|true|none||单号|
|»»» match|integer|true|none||是否匹配 0:不匹配 1:匹配|
|»»» travelReason|string|true|none||事由|
|»»» costCenterList|[object]|true|none||成本中心|
|»»»» id|integer|true|none||none|
|»»»» pid|integer|true|none||none|
|»»»» depId|string|true|none||成本中心ID|
|»»»» projectGroup|string|true|none||项目名称|
|»»»» discount|string|true|none||none|
|»»»» budgetCode|string|true|none||预算编码|
|»»»» belongCompany|string|true|none||费用归属公司|
|»»»» belongCompanyCode|string|true|none||费用归属公司编码|
|»»»» belongProjectCode|string|true|none||项目归属编码|
|»»»» depName|string|true|none||成本中心名称|
|»»»» accountType|string|true|none||结账类型|
|»»»» costCode|string|true|none||成本中心code|
|»»» passengerList|[object]|true|none||none|
|»»»» id|integer|true|none||none|
|»»»» pid|integer|true|none||none|
|»»»» userCode|string|true|none||工号|
|»»»» userName|string|true|none||姓名|
|»»»» cardType|string|true|none||证件类型|
|»»»» cardId|string|true|none||证件号|
|»»»» remark|string|true|none||备注|
|»»»» tel|string|true|none||电话|
|»»»» depName|string|true|none||成本中心名称|
|»» mileageCardList|[object]|true|none||里程卡|
|»»» code|string|true|none||发卡航|
|»»» airCode|string|true|none||航司编码|
|»»» airName|string|true|none||航司名称|
|»» insuranceList|[object]|true|none||保险|
|»»» insuranceId|string|true|none||保险价格|
|»»» insurancePrice|string|true|none||保险金额|
|»»» insuranceName|string|true|none||保险名称|
|»»» insuranceDesc|string|true|none||保险说明|
|»» airLineList|[object]|true|none||航段数据|
|»»» serialNumber|string|true|none||序列号|
|»»» groupList|[object]|true|none||航段组 与查询返回一致|
|»»» otherPriceList|[object]|true|none||其它程最低价格|
|»»»» id|string|true|none||第几程数据|
|»»»» tax|string|true|none||税费|
|»»»» price|string|true|none||票价|
|»»»» totalPrice|string|true|none||总价|
|»»»» serviceFee|string|true|none||公费服务费|
|»»» baggageList|[object]|true|none||行李额|
|»»»» id|string|true|none||none|
|»»»» baggageType|string|true|none||none|
|»»»» pieces|string|true|none||none|
|»»»» weight|string|true|none||none|
|»»»» totalWeight|string|true|none||none|
|»»»» textEn|string|true|none||none|
|»»»» textCh|string|true|none||none|
|»»»» sizeText|string|true|none||none|
|»»» flightAttributeMap|[object]|true|none||航班属性列表|
|»»»» uniqueId|integer|true|none||none|
|»»»» cabClassList|[object]|true|none||none|
|»»»»» cabClass|string|true|none||舱等|
|»»»»» wifi|string|true|none||是否有wifi 所有FULL航班全部有wifi的才会标记true 整个飞机全部（Full）覆盖才会标记为true|
|»»»»» power|string|true|none||是否有电源|
|»»»»» seat|object|true|none||座椅|
|»»»»»» pitch|string|true|none||坐椅前后间距, 坐椅最前端与前面坐椅椅背的距离|
|»»»»»» flatness|string|true|none||F: 完全倾斜 180 度平躺 A: 倾斜成一定角度 N: 不能完全平躺|
|»»»»»» width|string|true|none||S： 标准 W： 更宽 为空表示暂无数据|
|»»»» field_140|string|true|none||none|
|»»» cityList|[object]|true|none||航空城市列表|
|»»»» airPortCode|string|true|none||机场三字码|
|»»»» cityName|string|true|none||城市名称|
|»»»» airPortName|string|true|none||机场名称|
|»»»» countryName|string|true|none||国家名|
|»»»» cityCode|string|true|none||城市三字码|
|»»» airwayList|[object]|true|none||航空公司列表|
|»»»» companyNo|string|true|none||航空公司二字码|
|»»»» companyName|string|true|none||航空公司简称|
|»»»» fullCompanyName|string|true|none||航空公司全称|
|»»»» pertainName|string|true|none||航空公司所属联盟|
|»»» typeList|[object]|true|none||机型列表|
|»»»» type|string|true|none||机型|
|»»»» airCom|string|true|none||航空公司|
|»»»» size|string|true|none||尺寸|
|»»»» name|string|true|none||名称|

## POST 获取员工所有地址 

POST /air/customer/getPassengerAllAddress

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "dataList": [
      {
        "flag": 0,
        "id": 0,
        "address": "string",
        "realName": "string",
        "mobile": "string",
        "province": "string",
        "city": "string",
        "area": "string",
        "district": "string",
        "postcode": "string",
        "current": true
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» dataList|[object]|false|none||none|
|»»» flag|number|true|none||标志 1:个人地址 2：成本中心地址 3：公司地址|
|»»» id|number|true|none||id 个人地址才有|
|»»» address|string|true|none||地址|
|»»» realName|string|true|none||姓名|
|»»» mobile|string|true|none||手机|
|»»» province|string|true|none||省|
|»»» city|string|true|none||市|
|»»» area|string|true|none||区|
|»»» district|string|true|none||街道地址|
|»»» postcode|string|true|none||邮编|
|»»» current|boolean|true|none||默认地址|

## POST 查找一个用户指定工号证件号日期区间的申请单列表 

POST /application/listOneUserApplicationsByUserCodeCertNoDateRange

一。日期区间不能超过31天
二。有全部申请单权限，userCode,certNo允许传空
三。productType允许传null,返回所有产品的申请单数据

> Body 请求参数

```json
{
  "productType": "string",
  "applicationSearchType": "APPLICANT",
  "startDate": "string",
  "endDate": "string",
  "travelDate": "string",
  "domesticAirLine": "string",
  "internationalAirLine": [
    {
      "serialKey": "string",
      "flightNumber": "string"
    }
  ],
  "internationalAirLineNew": [
    {
      "serialNumber": "string",
      "priceId": "string"
    }
  ],
  "hotelAirLine": {
    "city": "string",
    "cityId": "string",
    "startDate": "string",
    "endDate": "string",
    "avaprice": "string",
    "star": "string"
  },
  "trainAirLine": {
    "departStation": "string",
    "arriveStation": "string",
    "departDate": "string",
    "arriveDate": "string",
    "trainNo": "string",
    "seatType": "string"
  },
  "useCarAirLine": {
    "cityCode": "string",
    "useCarDate": "string",
    "useCarTime": "string",
    "carType": "string",
    "price": "string"
  },
  "oaApplicationId": 0,
  "applicationDh": "string",
  "userCode": "string",
  "certNo": "string",
  "passengerList": [
    "string"
  ],
  "depId": "string",
  "projectName": "string",
  "returnMatchState": true,
  "field_2": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» productType|body|string| 是 ||产品类型 DOMESTIC(国内机票),INTERNATIONAL(国际机票),DOMESTIC_HOTEL(国内酒店),INTERNATIONAL_HOTEL(国际酒店),TRAIN(火车),CAR(用车)|
|» applicationSearchType|body|string| 是 ||申请单搜索类型 APPLICANT(申请人) TRAVELER(出差人)|
|» startDate|body|string| 是 ||开始日期|
|» endDate|body|string| 是 ||结束日期|
|» travelDate|body|string| 是 ||出差日期|
|» domesticAirLine|body|string| 是 ||国内机票行程 国内机票必传|
|» internationalAirLine|body|[object]| 是 ||国际机票行程 国际机票必传 internationalAirLine，internationalAirLineNew二选一|
|»» serialKey|body|string| 是 ||缓存Key|
|»» flightNumber|body|string| 是 ||航班Id|
|» internationalAirLineNew|body|[object]| 是 ||国际机票行程-新 国际机票必传 internationalAirLine，internationalAirLineNew二选一|
|»» serialNumber|body|string| 是 ||缓存序列号|
|»» priceId|body|string| 是 ||价格Id|
|» hotelAirLine|body|object| 是 ||酒店航程 酒店必传|
|»» city|body|string| 是 ||国内酒店城市中文名 例:深圳|
|»» cityId|body|string| 是 ||国际酒店城市id 例:3168|
|»» startDate|body|string| 是 ||入住日期|
|»» endDate|body|string| 是 ||离店日期|
|»» avaprice|body|string| 是 ||价格|
|»» star|body|string| 否 ||星级|
|» trainAirLine|body|object| 是 ||火车航程 火车必传|
|»» departStation|body|string| 是 ||出发站点|
|»» arriveStation|body|string| 是 ||到达站点|
|»» departDate|body|string| 是 ||出发日期|
|»» arriveDate|body|string| 是 ||到达日期|
|»» trainNo|body|string| 是 ||车次|
|»» seatType|body|string| 是 ||座位类型|
|» useCarAirLine|body|object| 是 ||none|
|»» cityCode|body|string| 是 ||用车城市代号|
|»» useCarDate|body|string| 是 ||用车日期|
|»» useCarTime|body|string| 是 ||用车时间 格式HH:mm|
|»» carType|body|string| 是 ||服务车型，1 出租车（暂无该车型）；2 新能源；3 舒适型；4 豪华型；5 商务型|
|»» price|body|string| 是 ||预估价格，单位分|
|» oaApplicationId|body|integer| 是 ||oa申请单id 非空,返回此笔数据,且判断是否匹配|
|» applicationDh|body|string| 否 ||申请单号 模糊查找|
|» userCode|body|string| 否 ||工号|
|» certNo|body|string| 否 ||证件号|
|» passengerList|body|[string]| 否 ||乘机人列表|
|» depId|body|string| 否 ||成本中心|
|» projectName|body|string| 否 ||项目组|
|» returnMatchState|body|boolean| 是 ||返回匹配状态 false:不计算申请单是否匹配|
|» field_2|body|string| 是 ||none|

#### 枚举值

|属性|值|
|---|---|
|» applicationSearchType|APPLICANT|
|» applicationSearchType|TRAVELER|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "application": {
      "clientID": "string",
      "dh": "string",
      "match": true
    }
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» application|object|false|none||none|
|»»» clientID|string|false|none||申请单id|
|»»» dh|string|false|none||申请单号|
|»»» match|boolean|false|none||是否匹配|

## POST 乘机人查询 

POST /air/customer/findPassenger

> Body 请求参数

```json
{
  "data": "string",
  "containtData": "string",
  "pageIndex": 0,
  "pageSize": 0,
  "type": 0,
  "clientIdSpecify": "string",
  "productType": "DOMESTIC"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» data|body|string| 否 ||查找内容|
|» containtData|body|string| 否 ||查找包含内容|
|» pageIndex|body|integer| 否 ||页码|
|» pageSize|body|integer| 否 ||页大小|
|» type|body|integer| 否 ||查找类型 0:姓名 1：证件号|
|» clientIdSpecify|body|string| 否 ||指定客户|
|» productType|body|string| 是 ||产品类型 DOMESTIC:国内机票(默认) INTERNATIONAL:国际机票 DOMESTIC_HOTEL:国内酒店 INTERNATIONAL_HOTEL:国际酒店 TRAIN:火车|

#### 枚举值

|属性|值|
|---|---|
|» productType|DOMESTIC|
|» productType|INTERNATIONAL|
|» productType|DOMESTIC_HOTEL|
|» productType|INTERNATIONAL_HOTEL|
|» productType|TRAIN|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "dataList": [
      {
        "id": 0,
        "userID": 0,
        "passengerName": "string",
        "certNo": "string",
        "certType": "string",
        "certName": "string",
        "certNamePinyin": "string",
        "sex": "string",
        "userCode": "string",
        "email": "string",
        "depId": 0,
        "depName": "string",
        "accountBank": "string",
        "birthDay": "string",
        "nationality": "string",
        "nationalityName": "string",
        "expiryDate": "string",
        "ageLevel": 0,
        "telList": [
          {
            "tel": null,
            "id": null,
            "pid": null
          }
        ]
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» dataList|[object]|false|none||数据列表|
|»»» id|number|true|none||证件id|
|»»» userID|number|true|none||用户id|
|»»» passengerName|string|true|none||姓名|
|»»» certNo|string|true|none||证件号|
|»»» certType|string|true|none||证件类型|
|»»» certName|string|true|none||证件名|
|»»» certNamePinyin|string|true|none||证件名拼音|
|»»» sex|string|true|none||性别|
|»»» userCode|string|true|none||用户代号|
|»»» email|string|true|none||邮箱|
|»»» depId|number|true|none||部门id|
|»»» depName|string|true|none||部门|
|»»» accountBank|string|true|none||开户银行|
|»»» birthDay|string|true|none||生日|
|»»» nationality|string|true|none||国籍代码|
|»»» nationalityName|string|true|none||国籍|
|»»» expiryDate|string|true|none||证件有效期|
|»»» ageLevel|integer|true|none||年龄等级 0:>=18且<70(成人)  1:>=12且<18(青年)  2:<12(儿童)  3:>=70(老人)|
|»»» telList|[object]|true|none||none|
|»»»» tel|string|true|none||电话|
|»»»» id|number|true|none||none|
|»»»» pid|number|true|none||none|

## POST 签证提醒 

POST /air/international/visa

> Body 请求参数

```json
{
  "fromCity": "string",
  "stopCity": "string",
  "toCity": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» fromCity|body|string| 否 ||出发城市三字码|
|» stopCity|body|string| 否 ||中转城市三字码（多个,分隔）|
|» toCity|body|string| 否 ||目的城市|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "visaDetails": "string"
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||标识，0：成功，其他：错误|
|» errorMsg|string|false|none||错误信息|
|» requestSeqNo|string|false|none||请求序号|
|» data|object|false|none||none|
|»» visaDetails|string|false|none||签证提醒|

## POST 订单保存

POST /air/international/saveOrder

> Body 请求参数

```json
{
  "outlayType": "string",
  "interfaceSupplier": "string",
  "savePassenger": "string",
  "clientId": "string",
  "payType": "string",
  "orderer": "string",
  "orderTel": "string",
  "userCode": "string",
  "orderMail": "string",
  "noadvanceReason": "string",
  "applicationDh": "string",
  "applicationId": "string",
  "depId": "string",
  "projectName": "string",
  "belongProjectCode": "string",
  "belongCompany": "string",
  "belongCompanyCode": "string",
  "depName": "string",
  "receiver": {
    "contact": "string",
    "clientTel": "string",
    "sendAddress": "string"
  },
  "needAddress": "string",
  "deliverType": "string",
  "budgetCode": "string",
  "addedTax": "string",
  "invoiceEmail": "string",
  "customerOrderId": "string",
  "specificPolicy": true,
  "travelPolicyList": [
    {
      "id": "string",
      "reason": "string"
    }
  ],
  "passengerList": [
    {
      "cardId": 0,
      "name": "string",
      "passengerName": "string",
      "passengerType": "string",
      "issueCountry": "string",
      "nationality": "string",
      "idType": "string",
      "userCode": "string",
      "depId": 0,
      "idNumber": "string",
      "idExpiration": "string",
      "gender": "string",
      "birthday": "string",
      "phoneNumber": "string",
      "bx1": 0,
      "bx2": 0,
      "mileageList": [
        {
          "airId": "string",
          "mileageCardAirId": "string",
          "mileageCard": "string"
        }
      ]
    }
  ],
  "flightList": [
    {
      "serialNumber": "string",
      "priceId": "string",
      "pricingId": "string"
    }
  ],
  "additionalList": [
    {
      "id": "string",
      "code": "string",
      "name": "string",
      "noteText": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» outlayType|body|string| 否 ||费用类型：0：自费，1：公费|
|» interfaceSupplier|body|string| 否 ||接口来源|
|» savePassenger|body|string| 否 ||是否保存乘车人信息|
|» clientId|body|string| 否 ||指定客户ID|
|» payType|body|string| 否 ||支付方式：0：挂账，3：在线支付，4：银行转账|
|» orderer|body|string| 否 ||联系人姓名|
|» orderTel|body|string| 否 ||联系人手机|
|» userCode|body|string| 否 ||联系人工号|
|» orderMail|body|string| 否 ||联系人邮箱|
|» noadvanceReason|body|string| 否 ||出差事由|
|» applicationDh|body|string| 否 ||出差申请单单号|
|» applicationId|body|string| 否 ||出差申请单ID|
|» depId|body|string| 否 ||成本中心|
|» projectName|body|string| 否 ||项目名称|
|» belongProjectCode|body|string| 否 ||项目编码|
|» belongCompany|body|string| 否 ||归属公司|
|» belongCompanyCode|body|string| 否 ||归属公司编码|
|» depName|body|string| 否 ||成本中心名称|
|» receiver|body|object| 否 ||收货人信息|
|»» contact|body|string| 否 ||收货人名称|
|»» clientTel|body|string| 否 ||收货人电话|
|»» sendAddress|body|string| 否 ||收货人地址|
|» needAddress|body|string| 否 ||需要送货地址，1：需要送货地址；其他：不需要|
|» deliverType|body|string| 否 ||送货方式，2：单独配送，3：免送货|
|» budgetCode|body|string| 否 ||预算编码|
|» addedTax|body|string| 否 ||纸质增值税 普通发票|
|» invoiceEmail|body|string| 否 ||邮箱|
|» customerOrderId|body|string| 否 ||客户订单号|
|» specificPolicy|body|boolean| 否 ||有政策并符合，就为true，否则为false|
|» travelPolicyList|body|[object]| 否 ||none|
|»» id|body|string| 否 ||政策ID|
|»» reason|body|string| 否 ||原因|
|» passengerList|body|[object]| 否 ||none|
|»» cardId|body|integer| 否 ||证件表ID|
|»» name|body|string| 否 ||乘客姓名，格式： Zhang/San|
|»» passengerName|body|string| 否 ||中文名称|
|»» passengerType|body|string| 否 ||乘客类型，0：成人 1：儿童 2：婴儿 3：老人 4：学生 5：劳务 6：移民 7：海员 8：青年|
|»» issueCountry|body|string| 否 ||发证国家, CN中国|
|»» nationality|body|string| 否 ||国籍代码|
|»» idType|body|string| 否 ||证件类型，0：护照 ，1：港澳通行证，2：台胞证，3：回乡证，4：台湾通行证|
|»» userCode|body|string| 否 ||工号|
|»» depId|body|integer| 否 ||部门ID|
|»» idNumber|body|string| 否 ||证件号码|
|»» idExpiration|body|string| 否 ||证件有效期|
|»» gender|body|string| 否 ||性别 1：男 0：女|
|»» birthday|body|string| 否 ||生日|
|»» phoneNumber|body|string| 否 ||手机号，航司规定，多成人不可重复，目前MU,HU,SQ,MI限制必输|
|»» bx1|body|integer| 否 ||保险1的数量|
|»» bx2|body|integer| 否 ||保险2的数量|
|»» mileageList|body|[object]| 否 ||里程卡列表|
|»»» airId|body|string| 否 ||航司二字码|
|»»» mileageCardAirId|body|string| 否 ||里程卡航司二字码|
|»»» mileageCard|body|string| 否 ||里程卡号|
|» flightList|body|[object]| 是 ||none|
|»» serialNumber|body|string| 是 ||序列号|
|»» priceId|body|string| 是 ||价格ID|
|»» pricingId|body|string| 是 ||核价Id，对应核价返回的priceId|
|» additionalList|body|[object]| 否 ||none|
|»» id|body|string| 否 ||其础数据id|
|»» code|body|string| 否 ||数据编号|
|»» name|body|string| 否 ||基础数据名称|
|»» noteText|body|string| 否 ||文本备注信息|

> 返回示例

> 200 Response

```json
{
  "errorMsg": "string",
  "errorCode": "string",
  "enErrorMsg": "string",
  "data": {
    "msg": "string",
    "orderGroupId": "string",
    "pnr": "string",
    "orderClientInvoiceTypeRate": {
      "invoiceType": "string",
      "electronic": true,
      "taxRate": "string"
    },
    "orderList": [
      {
        "orderId": "string",
        "subOrderId": "string",
        "pnrState": "string",
        "pnrNo": "string",
        "recPrice": 0
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

*empty object*

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorMsg|string|true|none||none|
|» errorCode|string|true|none||none|
|» enErrorMsg|string|true|none||none|
|» data|object|true|none||none|
|»» msg|string|true|none||错误信息|
|»» orderGroupId|string|true|none||订单组号|
|»» pnr|string|true|none||PRN|
|»» orderClientInvoiceTypeRate|object|true|none||订单开票信息|
|»»» invoiceType|string|true|none||发票类型 SPECIAL_INVOICE(专票),GENERAL_INVOICE(普票),TRAVELITINERARY(行程单),DIGITAL_TRAVELITINERARY(数电行程单)|
|»»» electronic|boolean|true|none||是否电子|
|»»» taxRate|string|true|none||发票税率 1.电子发票税率6%；2.国内机票：电子行程单9%；3.国际机票：纸质行程单0%|
|»» orderList|[object]|true|none||订单列表|
|»»» orderId|string|true|none||订单号|
|»»» subOrderId|string|true|none||副订单号|
|»»» pnrState|string|true|none||PNR状态|
|»»» pnrNo|string|true|none||PNR号|
|»»» recPrice|number|true|none||应付款|

## POST 客户基本数据 

POST /air/customer/getClientBasicData

> Body 请求参数

```json
{
  "clientId": "string",
  "official": true,
  "productType": "DOMESTIC"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|
|» clientId|body|string| 否 ||指定客户ID|
|» official|body|boolean| 否 ||是否公务员|
|» productType|body|string| 是 ||枚举说明: 分别为：国内机票，国际机票，国内酒店，国际酒店，火车，用车，签证|

#### 枚举值

|属性|值|
|---|---|
|» productType|DOMESTIC|
|» productType|INTERNATIONAL|
|» productType|DOMESTIC_HOTEL|
|» productType|INTERNATIONAL_HOTEL|
|» productType|TRAIN|
|» productType|CAR|
|» productType|VISA|

> 返回示例

> 200 Response

```json
{
  "tmsErrorCode": "string",
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "delay": 0,
  "data": {
    "userId": 0,
    "userCode": "string",
    "email": "string",
    "depId": 0,
    "clientName": "string",
    "vipId": "string",
    "clientRank": "string",
    "pactStartD": "string",
    "pactEndD": "string",
    "tel": "string",
    "email_company": "string",
    "address": "string",
    "approveType": "string",
    "accMonDate": "string",
    "salesMan": "string",
    "reconciliation": "string",
    "integral": "string",
    "havdPoint": "string",
    "personalIntegral": "string",
    "personalHavdPoint": "string",
    "credit_line": "string",
    "openid": "string",
    "enterpriseClient": true,
    "accountType": "string",
    "approvalOa": true,
    "refundType": "NON_REFUND",
    "hideDomesticService": true,
    "hideInternationService": true,
    "hideHotelService": true,
    "hideTrainService": true,
    "costCenter": "HIDE",
    "costCenterCode": "string",
    "projectFlag": "string",
    "belongProjectCode": "string",
    "belongCompany": "string",
    "belongCompanyCode": "string",
    "ticketDep": "HIDE",
    "ticketUserCode": "string",
    "trainDep": "string",
    "autoInsertPassenger": true,
    "defaultShowShareId": true,
    "defaultShowInternationShareId": true,
    "domesticTransshipment": true,
    "hidePriceDetail": true,
    "etermVerification": "string",
    "thirdPricePoundage": 0,
    "showThirdPrice": 0,
    "ticketDiffDays": 0,
    "ticketDiffDaysBehind": 0,
    "hotelDiffDays": 0,
    "hotelDiffDaysBehind": 0,
    "trainDiffDays": 0,
    "trainDiffDaysBehind": 0,
    "carDiffDays": 0,
    "carDiffDaysBehind": 0,
    "applicationRestrictCols": 0,
    "applicationMatchCols": 0,
    "applicationMatch": "BACKSTAGE",
    "applicationRegular": "string",
    "applicationRegularHint": "string",
    "applicationType": "NON_APPLICATION",
    "budgetCode": "string",
    "budgetCodeRegular": "string",
    "budgetCodeRegularHint": "string",
    "homeBackGotoUrl": "string",
    "allowApply": true,
    "oaApplicationDefaultGo": true,
    "otherSameAsSelf": true,
    "orderReason": true,
    "tgzReason": true,
    "officialCustomer": true,
    "insurance": "NON_BUY",
    "internationalInsurance": "string",
    "showDomesticPlane": true,
    "showInternational": true,
    "showHotel": true,
    "showInternationalHotel": true,
    "showTrain": true,
    "showUseCar": true,
    "showVisa": true,
    "showPriceText": true,
    "showCtripTitle": true,
    "hideBirthday": true,
    "hideCertNo": true,
    "options": 0,
    "orderer": "string",
    "orderTel": "string",
    "idCard": "string",
    "applicationCanNoInput": true,
    "applicationNoInputCash": true,
    "applicationNoMatchNoContinue": true,
    "applicationNoMatchCash": true,
    "applicationCanNoInputChangeSign": true,
    "applicationNoInputCashChangeSign": true,
    "applicationNoMatchNoContinueChangeSign": true,
    "applicationNoMatchCashChangeSign": true,
    "gnTicketExcludeAirIdList": "string",
    "hotelTrusteeship": 0,
    "hotelTrusteeshipChainGroup": 0,
    "hideHotelStarLevel": 0,
    "ticketCanGz": true,
    "hotelCanGz": true,
    "internationalHotelCanGz": true,
    "trainCanGz": true,
    "useCarCanGz": true,
    "showPublicSet": true,
    "showSelfSet": true,
    "showQunar": true,
    "showCtrip": true,
    "showHbgj": true,
    "showCh": true,
    "allowSpecifyClient": true,
    "applicationApproveNotice": true,
    "hotelViolatePolicy": [
      0
    ],
    "verifyHotelPolicy": true,
    "hotelPolicyCompliance": 0,
    "hotelRefundApprove": 0,
    "hotelChangeApprove": 0,
    "orderDataPermit": 0,
    "hotelApplicationCanNoInput": true,
    "hotelApplicationNoInputCash": true,
    "hotelApplicationNoMatchNoContinue": true,
    "hotelApplicationNoMatchCash": true,
    "hotelPolicyPriorApplication": true,
    "reportShowGroupClient": true,
    "onlyAirOrderSelfChannel": true,
    "onlyInternationalAirOrderSelfChannel": true,
    "onlyDomesticHotelOrderSelfChannel": true,
    "onlyInternationalHotelOrderSelfChannel": true,
    "onlyTrainOrderSelfChannel": true,
    "onlyCarOrderSelfChannel": true,
    "noShowIntegralInBasic": true,
    "autoConfirmTicket": true,
    "autoConfirmHotel": true,
    "autoConfirmHotelExcludeDiffPay": true,
    "autoConfirmTrain": true,
    "autoConfirmUseCar": true,
    "autoConfirmUseCarExcludeDiffPay": true,
    "orderPolicyViolation": "string",
    "czMember": true,
    "showNoUseTicket": true,
    "cabClassType": true,
    "cabClassList": [
      "string"
    ],
    "appImg": "string",
    "cartCnt": 0,
    "cartWorldCnt": "string",
    "phoneCountry": "string",
    "phoneShenzhen": "string",
    "systemSupplier": "string",
    "systemSupplierForTicket": "string",
    "companyLogo": "string",
    "myTicket": true,
    "myHotel": true,
    "myTrain": true,
    "myCar": true,
    "ticketReserve": true,
    "ticketApplication": true,
    "ticketReject": true,
    "ticketIssueProcess": true,
    "ticketPay": true,
    "ticketDealIOU": true,
    "ticketCancel": true,
    "hotelReserve": true,
    "hotelApplication": true,
    "hotelReject": true,
    "hotelReady": true,
    "hotelAffirm": true,
    "hotelEnter": true,
    "hotelCancel": true,
    "trainReserve": true,
    "trainApplication": true,
    "trainReject": true,
    "trainAffirm": true,
    "trainEnter": true,
    "trainCancel": true,
    "carDispatched": true,
    "carDriving": true,
    "carWaitPayment": true,
    "carCompleted": true,
    "carCancel": true,
    "businessManagement": true,
    "fundamentalInfo": [
      "string"
    ],
    "staffData": [
      "string"
    ],
    "permitManage": [
      "string"
    ],
    "applicationBasic": true,
    "clientReceivables": true,
    "dataAnalysis": true,
    "travelAnalysis": "string",
    "clientLogoUpload": true,
    "approvalOaTitle": "string",
    "trainSupplier": "string",
    "trainSupplierFreeLogin": "string",
    "trainAccountNo": "string",
    "helpPrintTrainSupplier": "string",
    "hideHotelPartner": true,
    "hotelDuplicationRemind": "STRONG",
    "hotelDisplayAllPrice": true,
    "travelPolicyReasons": [
      {
        "productType": "string",
        "policyType": "string",
        "reason": "string"
      }
    ],
    "fhkLowprice": 0,
    "customerTaxNumber": "string",
    "hideOnlinePayments": [
      "AIR"
    ],
    "applicationCanSelectAll": true,
    "prohibitAppendTravelers": [
      "DOMESTIC"
    ],
    "displayGroupName": "string",
    "clientGroupClientId": "string",
    "planeOfficialSelfMergesort": true,
    "planeCalcDiscountByCabclass": true,
    "orderDataRange": 0,
    "myselfDefaultOrderSearchDate": "string",
    "departDefaultOrderSearchDate": "string",
    "allDefaultOrderSearchDate": "string",
    "oaLogin": true,
    "oaApplicationId": 0
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» tmsErrorCode|string|false|none||none|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» delay|number|false|none||none|
|» data|object|false|none||none|
|»» userId|number|false|none||当前用户id|
|»» userCode|string|false|none||当前用户工号|
|»» email|string|true|none||email|
|»» depId|integer|true|none||当前用户成本中心id|
|»» clientName|string|false|none||客户名称|
|»» vipId|string|true|none||会员卡号|
|»» clientRank|string|true|none||客户等级 普通客户,VIP客户,公务客户|
|»» pactStartD|string|true|none||合同有效始期|
|»» pactEndD|string|true|none||合同有效止期|
|»» tel|string|true|none||公司电话|
|»» email_company|string|true|none||公司邮箱|
|»» address|string|true|none||公司地址|
|»» approveType|string|true|none||送单周期 日送,周送,半月送,月送|
|»» accMonDate|string|true|none||付款天数|
|»» salesMan|string|true|none||业务员|
|»» reconciliation|string|true|none||对账员|
|»» integral|string|true|none||对公总积分|
|»» havdPoint|string|true|none||对公已兑积分|
|»» personalIntegral|string|true|none||对私总积分|
|»» personalHavdPoint|string|true|none||对私已兑积分|
|»» credit_line|string|true|none||授信额度|
|»» openid|string|false|none||微信openid|
|»» enterpriseClient|boolean|false|none||是否企业客户|
|»» accountType|string|false|none||结账类型|
|»» approvalOa|boolean|false|none||OA审批|
|»» refundType|string|false|none||枚举说明: 分别代表：不返；待返；现返。|
|»» hideDomesticService|boolean|false|none||隐藏国内机票服务费|
|»» hideInternationService|boolean|false|none||隐藏国际机票服务费|
|»» hideHotelService|boolean|false|none||隐藏酒店服务费|
|»» hideTrainService|boolean|false|none||隐藏火车服务费|
|»» costCenter|string|false|none||枚举说明: 分别代表为：隐藏；显示；显示并且输入或必填。|
|»» costCenterCode|string|false|none||成本中心编码(同上)|
|»» projectFlag|string|false|none||项目名称(同上)|
|»» belongProjectCode|string|false|none||项目编码(同上)|
|»» belongCompany|string|false|none||归属公司编码(同上)|
|»» belongCompanyCode|string|false|none||归属公司编码(同上)|
|»» ticketDep|string|false|none||枚举说明: 分别代表：不显示，显示|
|»» ticketUserCode|string|false|none||机票工号(同上)|
|»» trainDep|string|false|none||火车部门(同上)|
|»» autoInsertPassenger|boolean|false|none||自动新增乘机人|
|»» defaultShowShareId|boolean|false|none||默认显示国内共享|
|»» defaultShowInternationShareId|boolean|false|none||默认显示国际共享|
|»» domesticTransshipment|boolean|false|none||国内机票中转|
|»» hidePriceDetail|boolean|false|none||隐藏运价明细|
|»» etermVerification|string|false|none||系统信息-Eterm验证|
|»» thirdPricePoundage|number|false|none||第三方运价手续费|
|»» showThirdPrice|number|false|none||显示运价 1:去哪儿 2:携程 4:腾邦 8:航班管家 16:春秋航空 32:IBE 64:华夏接口|
|»» ticketDiffDays|integer|false|none||申请单机票延期天数前|
|»» ticketDiffDaysBehind|integer|false|none||申请单机票延期天数后|
|»» hotelDiffDays|integer|false|none||申请单酒店延期天数前|
|»» hotelDiffDaysBehind|integer|false|none||申请单酒店延期天数后|
|»» trainDiffDays|integer|false|none||申请单火车延期天数前|
|»» trainDiffDaysBehind|integer|false|none||申请单火车延期天数后|
|»» carDiffDays|integer|false|none||申请单用车延期天数前|
|»» carDiffDaysBehind|integer|false|none||申请单用车延期天数后|
|»» applicationRestrictCols|number|false|none||申请单必传栏位|
|»» applicationMatchCols|number|false|none||申请单必匹配栏位|
|»» applicationMatch|string|false|none||枚举说明: 分别代表为：按后台设置；按申请单设置|
|»» applicationRegular|string|false|none||申请单输入规则|
|»» applicationRegularHint|string|false|none||申请单输入规则提示|
|»» applicationType|string|false|none||枚举说明: 分别表示：无申请单；人工输入；oa导入|
|»» budgetCode|string|false|none||预算编码(同机票部门)|
|»» budgetCodeRegular|string|false|none||预算编码输入规则|
|»» budgetCodeRegularHint|string|false|none||预算编码输入规则提示|
|»» homeBackGotoUrl|string|false|none||查询页退回跳转网址|
|»» allowApply|boolean|false|none||允许点申请出票按钮|
|»» oaApplicationDefaultGo|boolean|false|none||出差单跳转默认单程|
|»» otherSameAsSelf|boolean|false|none||自营代购相同按钮|
|»» orderReason|boolean|false|none||订票事由|
|»» tgzReason|boolean|false|none||退改签事由|
|»» officialCustomer|boolean|false|none||公务客户|
|»» insurance|string|false|none||枚举说明: 分别代表为：不买；赠送；购买|
|»» internationalInsurance|string|false|none||国际保险(同上)|
|»» showDomesticPlane|boolean|false|none||显示国内机票|
|»» showInternational|boolean|false|none||显示国际机票|
|»» showHotel|boolean|false|none||显示国内酒店|
|»» showInternationalHotel|boolean|false|none||显示国际酒店|
|»» showTrain|boolean|false|none||显示火车|
|»» showUseCar|boolean|false|none||显示用车|
|»» showVisa|boolean|true|none||显示签证|
|»» showPriceText|boolean|false|none||显示航班文本|
|»» showCtripTitle|boolean|false|none||显示携程名字|
|»» hideBirthday|boolean|false|none||隐藏乘机人身份证号码|
|»» hideCertNo|boolean|false|none||隐藏乘机人其它证件号码|
|»» options|number|false|none||其它选项|
|»» orderer|string|false|none||订货人|
|»» orderTel|string|false|none||订货人电话|
|»» idCard|string|false|none||身份证号码|
|»» applicationCanNoInput|boolean|false|none||订票无需出差申请单|
|»» applicationNoInputCash|boolean|false|none||订票未填出差申请单，须现付|
|»» applicationNoMatchNoContinue|boolean|false|none||未匹配出差申请，不能下单|
|»» applicationNoMatchCash|boolean|false|none||未匹配出差申请，现付下单|
|»» applicationCanNoInputChangeSign|boolean|false|none||改签无需出差申请单|
|»» applicationNoInputCashChangeSign|boolean|false|none||改签未填出差申请单，须现付|
|»» applicationNoMatchNoContinueChangeSign|boolean|false|none||改签未匹配出差申请，不能下单|
|»» applicationNoMatchCashChangeSign|boolean|false|none||改签未匹配出差申请，现付下单|
|»» gnTicketExcludeAirIdList|string|false|none||国内查询过滤航司|
|»» hotelTrusteeship|number|false|none||酒店托管 会有多个|
|»» hotelTrusteeshipChainGroup|number|false|none||酒店托管连锁集团  会有多个|
|»» hideHotelStarLevel|number|false|none||屏蔽?星级及以上酒店|
|»» ticketCanGz|boolean|false|none||国内机票可挂账|
|»» hotelCanGz|boolean|false|none||国内酒店可挂账|
|»» internationalHotelCanGz|boolean|false|none||国际酒店可挂账|
|»» trainCanGz|boolean|false|none||火车可挂账|
|»» useCarCanGz|boolean|false|none||用车可挂账|
|»» showPublicSet|boolean|false|none||显示公费标签|
|»» showSelfSet|boolean|false|none||显示自费标签|
|»» showQunar|boolean|false|none||显示去哪儿|
|»» showCtrip|boolean|false|none||显示携程|
|»» showHbgj|boolean|false|none||显示航班管家|
|»» showCh|boolean|false|none||显示春秋航空|
|»» allowSpecifyClient|boolean|false|none||允许选客户名下单|
|»» applicationApproveNotice|boolean|false|none||出差单审批通知|
|»» hotelViolatePolicy|[integer]|false|none||酒店违法政策处理 1-现付下单 2-差额补现|
|»» verifyHotelPolicy|boolean|false|none||需遵守酒店差旅政策|
|»» hotelPolicyCompliance|number|false|none||酒店差旅政策遵守：0-订房人，1-入住人（同住人）|
|»» hotelRefundApprove|number|false|none||酒店退审批：0-退房无需审批，1-退房费需审批，2-退房直接确认|
|»» hotelChangeApprove|number|false|none||酒店改审批：0-改签无需审批，1-改签费需审批，2-改签直接确认|
|»» orderDataPermit|number|false|none||订单数据权限 0:本人 1:公司 2:部门|
|»» hotelApplicationCanNoInput|boolean|false|none||酒店订票无需出差申请单|
|»» hotelApplicationNoInputCash|boolean|false|none||酒店订票未填出差申请单，须现付|
|»» hotelApplicationNoMatchNoContinue|boolean|false|none||酒店未匹配出差申请，不能下单|
|»» hotelApplicationNoMatchCash|boolean|false|none||酒店未匹配出差申请，现付下单|
|»» hotelPolicyPriorApplication|boolean|false|none||酒店遵守差旅政策优先出差单|
|»» reportShowGroupClient|boolean|false|none||分析报表查看集团|
|»» onlyAirOrderSelfChannel|boolean|false|none||限订本人(国内机票)|
|»» onlyInternationalAirOrderSelfChannel|boolean|false|none||限订本人(国际机票)|
|»» onlyDomesticHotelOrderSelfChannel|boolean|false|none||限订本人(国内酒店)|
|»» onlyInternationalHotelOrderSelfChannel|boolean|false|none||限订本人(国际酒店)|
|»» onlyTrainOrderSelfChannel|boolean|false|none||限订本人(火车票)|
|»» onlyCarOrderSelfChannel|boolean|false|none||限订本人(用车)|
|»» noShowIntegralInBasic|boolean|false|none||在我的基本资料里不显示积分返点|
|»» autoConfirmTicket|boolean|false|none||机票下单即确认|
|»» autoConfirmHotel|boolean|false|none||酒店下单即确认|
|»» autoConfirmHotelExcludeDiffPay|boolean|false|none||酒店下单即确认(差额支付除外)|
|»» autoConfirmTrain|boolean|false|none||火车下单即确认|
|»» autoConfirmUseCar|boolean|false|none||用车下单即确认|
|»» autoConfirmUseCarExcludeDiffPay|boolean|false|none||用车下单即确认(差额支付除外)|
|»» orderPolicyViolation|string|false|none||预订人机票政策违反处理 APPROVE:需审批 NO_CONTINUE:不能下单 CASH:现付下单|
|»» czMember|boolean|false|none||南航会员|
|»» showNoUseTicket|boolean|false|none||显示未使用机票|
|»» cabClassType|boolean|false|none||机票-查询-舱等--方式 false:按默认舱位查 true:按职务查|
|»» cabClassList|[string]|false|none||用户舱位等级列表|
|»» appImg|string|false|none||App二维码|
|»» cartCnt|number|false|none||国内购物车数量|
|»» cartWorldCnt|string|false|none||国际购物车数量|
|»» phoneCountry|string|false|none||全国电话|
|»» phoneShenzhen|string|false|none||深圳电话|
|»» systemSupplier|string|false|none||系统提供方|
|»» systemSupplierForTicket|string|false|none||系统提供方机票查询|
|»» companyLogo|string|false|none||公司logo|
|»» myTicket|boolean|false|none||我的机票|
|»» myHotel|boolean|false|none||我的酒店|
|»» myTrain|boolean|false|none||我的火车|
|»» myCar|boolean|false|none||我的用车|
|»» ticketReserve|boolean|false|none||机票预留中|
|»» ticketApplication|boolean|false|none||机票待审批|
|»» ticketReject|boolean|false|none||机票已拒绝|
|»» ticketIssueProcess|boolean|false|none||机票出票中|
|»» ticketPay|boolean|false|none||机票已出票|
|»» ticketDealIOU|boolean|false|none||机票还欠款|
|»» ticketCancel|boolean|false|none||机票取消的|
|»» hotelReserve|boolean|false|none||酒店预留中|
|»» hotelApplication|boolean|false|none||酒店待审批|
|»» hotelReject|boolean|false|none||酒店已拒绝|
|»» hotelReady|boolean|false|none||酒店订房中|
|»» hotelAffirm|boolean|false|none||酒店订房成功|
|»» hotelEnter|boolean|false|none||酒店订房失败|
|»» hotelCancel|boolean|false|none||酒店已取消|
|»» trainReserve|boolean|false|none||火车预留中|
|»» trainApplication|boolean|false|none||火车待审批|
|»» trainReject|boolean|false|none||火车已拒绝|
|»» trainAffirm|boolean|false|none||火车出票中|
|»» trainEnter|boolean|false|none||火车已出票|
|»» trainCancel|boolean|false|none||火车取消的|
|»» carDispatched|boolean|false|none||用车已派单|
|»» carDriving|boolean|false|none||用车行程中|
|»» carWaitPayment|boolean|false|none||用车待支付|
|»» carCompleted|boolean|false|none||用车已完成|
|»» carCancel|boolean|false|none||用车已取消|
|»» businessManagement|boolean|false|none||企业管理|
|»» fundamentalInfo|[string]|false|none||基本信息|
|»» staffData|[string]|false|none||none|
|»» permitManage|[string]|false|none||员工档案|
|»» applicationBasic|boolean|false|none||申请单|
|»» clientReceivables|boolean|false|none||应付账单|
|»» dataAnalysis|boolean|false|none||数据分析(old)|
|»» travelAnalysis|string|true|none||差旅分析 DEPARTMENT(本部门)，COMPANY(本公司)，GROUP(本集团)|
|»» clientLogoUpload|boolean|false|none||客户logo上传|
|»» approvalOaTitle|string|false|none||OA审批标签名|
|»» trainSupplier|string|false|none||Rsscc（高铁管家），Qunar（去哪儿），ChuXing（付讯）|
|»» trainSupplierFreeLogin|string|false|none||免登录火车供应商|
|»» trainAccountNo|string|false|none||12306账号 有值,代表有保存在我们系统|
|»» helpPrintTrainSupplier|string|false|none||代打火车供应商 高铁管家:Rsscc 去哪儿:Qunar 付迅:ChuXing 例:Rsscc|
|»» hideHotelPartner|boolean|false|none||隐藏酒店同住人|
|»» hotelDuplicationRemind|string|false|none||酒店--重复单提醒 STRONG:强管制 WEAK:弱管制|
|»» hotelDisplayAllPrice|boolean|false|none||酒店显示全部价|
|»» travelPolicyReasons|[object]|false|none||客户差旅政策原因列表|
|»»» productType|string|true|none||产品类型|
|»»» policyType|string|true|none||政策类型|
|»»» reason|string|true|none||原因|
|»» fhkLowprice|integer|true|none||航班管家运价<飞鹤价显示 <0:不限制|
|»» customerTaxNumber|string|true|none||客户税号|
|»» hideOnlinePayments|[string]|true|none||隐藏在线支付列表 AIR(机票),HOTEL(酒店),TRAIN(火车)|
|»» applicationCanSelectAll|boolean|false|none||全部出差单|
|»» prohibitAppendTravelers|[string]|false|none||禁增出差人 DOMESTIC:国内机票 INTERNATIONAL:国际机票 DOMESTIC_HOTEL:国内酒店 INTERNATIONAL_HOTEL:国际酒店 TRAIN:火车|
|»» displayGroupName|string|true|none||显示集团名称 权限里设置显示集团名称且客户有集团，会返回集团名称|
|»» clientGroupClientId|string|true|none||集团客户编号|
|»» planeOfficialSelfMergesort|boolean|true|none||机票查询官网自营合并排序|
|»» planeCalcDiscountByCabclass|boolean|true|none||按舱等计算折扣|
|»» orderDataRange|integer|true|none||/**      * 订单数据范围      * 订单数据      * 0-本人      * 1-全部      * 2-部门      */|
|»» myselfDefaultOrderSearchDate|string|true|none||本人默认订单数据日期范围 ONE_MONTH:一个月 THREE_MONTH:三个月 SIX_MONTH:半年 ONE_YEAR:一年|
|»» departDefaultOrderSearchDate|string|true|none||部门默认订单数据日期范围 SERVEN_DAY:7天 FIFTEEN_DAY:15天 ONE_MONTH:一个月|
|»» allDefaultOrderSearchDate|string|true|none||全部默认订单数据日期范围 SERVEN_DAY:7天 FIFTEEN_DAY:15天 ONE_MONTH:一个月|
|»» oaLogin|boolean|true|none||Oa登陆|
|»» oaApplicationId|integer|true|none||OA申请单ID|

#### 枚举值

|属性|值|
|---|---|
|refundType|NON_REFUND|
|refundType|WAIT_REFUND|
|refundType|NOW_REFUND|
|costCenter|HIDE|
|costCenter|DISPLAY|
|costCenter|DISPLAY_INPUT|
|ticketDep|HIDE|
|ticketDep|DISPLAY|
|applicationMatch|BACKSTAGE|
|applicationMatch|APPLICATION|
|applicationType|NON_APPLICATION|
|applicationType|MANUAL_INPUT|
|applicationType|OA_IMPORT|
|insurance|NON_BUY|
|insurance|GIVE|
|insurance|BUY|
|hotelDuplicationRemind|STRONG|
|hotelDuplicationRemind|WEAK|

## POST 基本数据 

POST /customer/mine/getMineBasicData

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "imgUrl": "string",
    "userName": "string",
    "companyName": "string",
    "companyId": "string",
    "invite": true,
    "userCode": "string",
    "type": "string",
    "sex": "string",
    "depId": 0,
    "depName": "string",
    "groupId": "string",
    "grade": "string",
    "email": "string",
    "position": "string",
    "telList": [
      "string"
    ],
    "certList": [
      {
        "id": 0,
        "certNo": "string",
        "certName": "string",
        "certType": "string",
        "remark": "string"
      }
    ],
    "mileageCardList": [
      {
        "id": "string",
        "airId": "string",
        "mileage_card": "string",
        "name": "string"
      }
    ],
    "permitGroupList": [
      {
        "roleId": "string",
        "roleName": "string",
        "memo": "string",
        "type": "string"
      }
    ],
    "mileageCardAirList": [
      {
        "ciS_ID": "string",
        "eCiS_Name": "string",
        "ciS_Name": "string"
      }
    ]
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» imgUrl|string|true|none||logo图地址|
|»» userName|string|true|none||登陆用户|
|»» companyName|string|true|none||公司名称|
|»» companyId|string|true|none||公司id|
|»» invite|boolean|true|none||是否邀请|
|»» userCode|string|true|none||用户代号|
|»» type|string|true|none||用户类型|
|»» sex|string|true|none||性别|
|»» depId|integer|true|none||用户默认成本中心ID|
|»» depName|string|true|none||用户默认成本中心名称|
|»» groupId|string|true|none||组ID|
|»» grade|string|true|none||等级|
|»» email|string|true|none||邮箱|
|»» position|string|true|none||职位|
|»» telList|[string]|true|none||手机列表|
|»» certList|[object]|true|none||证件列表|
|»»» id|integer|true|none||none|
|»»» certNo|string|true|none||证件号码|
|»»» certName|string|true|none||证明名称|
|»»» certType|string|true|none||证件类型|
|»»» remark|string|true|none||有效日期|
|»» mileageCardList|[object]|true|none||里程卡列表|
|»»» id|string|true|none||none|
|»»» airId|string|true|none||航司二字码|
|»»» mileage_card|string|true|none||里程卡号|
|»»» name|string|true|none||none|
|»» permitGroupList|[object]|true|none||权限组|
|»»» roleId|string|true|none||角色ID|
|»»» roleName|string|true|none||角色名称|
|»»» memo|string|true|none||备注|
|»»» type|string|true|none||角色类型 SELF:客户组 GLOBAL:系统组|
|»» mileageCardAirList|[object]|true|none||航司里程卡|
|»»» ciS_ID|string|true|none||航司二字码|
|»»» eCiS_Name|string|true|none||航司简称|
|»»» ciS_Name|string|true|none||航司全称|

## POST 首页-我的审批统计

POST /approve/mySelfApproveCount

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|

> 返回示例

> 200 Response

```json
{
  "tmsErrorCode": "string",
  "errorCode": "string",
  "errorMsg": "string",
  "enErrorMsg": "string",
  "requestSeqNo": "string",
  "delay": 0,
  "data": {
    "approveApplyNumber": 0,
    "approveTripNumber": 0,
    "noApproveApplyNumber": 0,
    "noApproveTripNumber": 0,
    "startApplyNumber": 0,
    "startTripNumber": 0
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» tmsErrorCode|string|false|none||none|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» enErrorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» delay|number|false|none||none|
|» data|object|false|none||none|
|»» approveApplyNumber|number|false|none||我审核的出差申请数量|
|»» approveTripNumber|number|false|none||我审核的差旅行程数量|
|»» noApproveApplyNumber|number|false|none||待我审批出差申请数量|
|»» noApproveTripNumber|number|false|none||待我审批差旅行程数量|
|»» startApplyNumber|number|false|none||我发起的出差申请数量|
|»» startTripNumber|number|false|none||我发起的差旅行程数量|

## POST 验证机票支付--新订单 

POST /air/domestic/getPlaneSendpki

一。<span class="colour" style="color:rgba(13, 27, 62, 0.65)">orderIsWholeCash为true,不允许切换支付方式，只能显示全额现付</span>
<span class="colour" style="color:rgba(13, 27, 62, 0.65)">二。此接口返回的</span>payType是来自订单付款表数据
三。<span class="colour" style="color:rgba(13, 27, 62, 0.65)">listMultipleOrdersPayType接口是根据下单时选择的付款表数据来显示，适用切换支付方式</span>
四。payType按下面优先级显示
         第一组：5：差额支付需审批  3：申请出票
         第二组：4：差额支付--部分现付 1:在线支付--全额现付
         第三组：2：我要出票
五。diffcashData对象不返回空，由挂账切换到差额支付或差旅支付切换到挂账才需要调用接口listMultipleOrdersPayType接口
六。支付页面显示的：您本次预订违反差标，超标金额固定取diffcashData对象的diffCashOrder

> Body 请求参数

```json
{
  "datatype": 0,
  "orderGroup": "string",
  "urlFrom": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» datatype|body|integer| 是 ||数据类型 0：订单组 1：订单号|
|» orderGroup|body|string| 否 ||订单组（0）或订单号（1）|
|» urlFrom|body|string| 否 ||页面来源|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "payType": 0,
    "paysTag": 0,
    "orderIsWholeCash": true,
    "optionsOfClient": 0,
    "allowApply": true,
    "applicationDiscount": "string",
    "smsApproval": true,
    "approve": true,
    "prepareApproverId": 0,
    "prepareApproverTel": "string",
    "prepareApproverMsg": "string",
    "approvalOa": true,
    "approvalTel": true,
    "approvalEmail": true,
    "approvalWx": true,
    "violatePolicy": true,
    "showViolatePolicy": true,
    "ticketTime": "string",
    "otherOrder": 0,
    "otherOrderPrice": "string",
    "flyDate": "string",
    "airLine": "string",
    "flightId": "string",
    "webPriceData": "string",
    "productType": "string",
    "sourceType": "string",
    "orderList": [
      {
        "orderId": "string",
        "otherOrder": 0,
        "createDate": "string",
        "ticketProductName": "string",
        "depNameOfOrderId": "string",
        "publicExpense": true,
        "recPrice": 0,
        "payPrice": 0,
        "airlineList": [
          {
            "type": null,
            "airLine": null,
            "fromPort": null,
            "toPort": null,
            "flyDate": null,
            "flyTime": null,
            "arriveDate": null,
            "arriveTime": null,
            "flightId": null,
            "shareId": null,
            "ticketNo": null,
            "price": null,
            "recPrice": null,
            "acf": null,
            "baf": null,
            "discount": null,
            "clientService": null,
            "cab": null,
            "cabClass": null,
            "cabName": null,
            "luggage": null,
            "tgzId": null,
            "transferFlight": null,
            "tripSeq": null,
            "legSeq": null
          }
        ],
        "payType": 0,
        "diffCash": 0,
        "diffCashOrder": 0,
        "paymentKind": "string",
        "productList": [
          {
            "name": null,
            "certNo": null,
            "productType": null,
            "productTypeGroup": null,
            "productMemo": null,
            "pretium": null,
            "productCount": null
          }
        ],
        "nameList": [
          {
            "name": null,
            "type": null,
            "partnerName": null,
            "certType": null,
            "certNo": null,
            "coach": null,
            "ticketNo": null
          }
        ],
        "orderPlaneTgqList": [
          {
            "type": null,
            "airId": null,
            "fromCity": null,
            "toCity": null,
            "cabin": null,
            "discount": null,
            "flyDate": null,
            "receiveDate": null,
            "refundRule": null,
            "changeRule": null,
            "issueRule": null
          }
        ]
      }
    ],
    "approveUserList": [
      {
        "id": 0,
        "name": "string",
        "depName": "string",
        "depId": 0,
        "phone": "string",
        "email": "string",
        "tel": "string",
        "sameDepId": true,
        "approverGroupId": 0,
        "approveRank": 0,
        "approveState": "string"
      }
    ],
    "travelPolicyList": [
      {
        "seq": 0,
        "policyJsonText": "string",
        "punish": "string",
        "reason": "string",
        "remark": "string",
        "requireReason": true,
        "policyValue": 0,
        "type": 0
      }
    ],
    "citys": [
      {
        "cityCode": "string",
        "cityName": "string",
        "airPortName": "string"
      }
    ],
    "airways": [
      {
        "companyNo": "string",
        "companyName": "string",
        "fullCompanyName": "string"
      }
    ],
    "orderBasicDataJson": "string",
    "diffcashData": {
      "orderChoiceDiffPrice": true,
      "diffCashOrder": 0
    }
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» payType|number|false|none||支付类型 1:在线支付--全额现付 2：我要出票 3：申请出票 4：差额支付--部分现付 5：差额支付需审批|
|»» paysTag|number|false|none||核价类型 0：还欠款，1：代购订单，2：正常订单|
|»» orderIsWholeCash|boolean|true|none||下单是否为全额现付--true不允许切换支付方式|
|»» optionsOfClient|number|false|none||客户选项|
|»» allowApply|boolean|false|none||允许点申请出票按钮|
|»» applicationDiscount|string|false|none||申请单折扣|
|»» smsApproval|boolean|false|none||是否短信审批|
|»» approve|boolean|false|none||是否多级审批|
|»» prepareApproverId|number|false|none||审批人ID|
|»» prepareApproverTel|string|false|none||审批人电话|
|»» prepareApproverMsg|string|false|none||审批人错误信息|
|»» approvalOa|boolean|false|none||OA审批,订单需要有申请单|
|»» approvalTel|boolean|false|none||短信审批|
|»» approvalEmail|boolean|false|none||邮箱审批|
|»» approvalWx|boolean|false|none||微信审批|
|»» violatePolicy|boolean|false|none||违反折扣政策|
|»» showViolatePolicy|boolean|false|none||是否显示违反折扣政策|
|»» ticketTime|string|false|none||出票时限|
|»» otherOrder|number|false|none||代购订单 1:去哪儿网 2:携程网 3:腾邦集团 4:航班管家 5:春秋航空|
|»» otherOrderPrice|string|false|none||代购订单价格|
|»» flyDate|string|false|none||代购订单乘机日|
|»» airLine|string|false|none||代购订单航程|
|»» flightId|string|false|none||代购订单航班号|
|»» webPriceData|string|false|none||代购订单核价|
|»» productType|string|false|none||产品类型 国内机票 国际机票|
|»» sourceType|string|false|none||来源类型 0:订单订座 1：其它|
|»» orderList|[object]|false|none||订单数据|
|»»» orderId|string|false|none||订单号 对应原来的order_id|
|»»» otherOrder|number|false|none||代购订单 1:去哪儿网 2:携程网 3:腾邦集团 4:航班管家 5:春秋航空 6:华夏航空|
|»»» createDate|string|false|none||下单日期|
|»»» ticketProductName|string|false|none||机票产品名称|
|»»» depNameOfOrderId|string|false|none||订货人部门|
|»»» publicExpense|boolean|true|none||公费,自费 对应原来的publicWeb|
|»»» recPrice|number|false|none||应付款|
|»»» payPrice|number|false|none||已付款|
|»»» airlineList|[object]|false|none||航程列表|
|»»»» type|string|false|none||none|
|»»»» airLine|string|false|none||航程|
|»»»» fromPort|string|false|none||出发航站楼|
|»»»» toPort|string|false|none||到达航站楼|
|»»»» flyDate|string|false|none||起飞日期|
|»»»» flyTime|string|false|none||起飞时间|
|»»»» arriveDate|string|false|none||降落日期|
|»»»» arriveTime|string|false|none||降落时间|
|»»»» flightId|string|false|none||航班号|
|»»»» shareId|string|false|none||共享航班号|
|»»»» ticketNo|string|false|none||票号|
|»»»» price|number|false|none||价格|
|»»»» recPrice|number|false|none||应收款|
|»»»» acf|number|false|none||机场建设费|
|»»»» baf|number|false|none||燃油附加费|
|»»»» discount|number|false|none||折扣|
|»»»» clientService|number|false|none||服务费|
|»»»» cab|string|false|none||舱位|
|»»»» cabClass|string|false|none||舱位等级|
|»»»» cabName|string|false|none||舱位名称|
|»»»» luggage|string|false|none||行李额|
|»»»» tgzId|string|false|none||退改签详情|
|»»»» transferFlight|integer|false|none||中转航班|
|»»»» tripSeq|string|true|none||航程NO 例:1代表第一程(去程)，2代表第二程(回程)|
|»»»» legSeq|string|true|none||航段NO 例:1代表第一段，2代表第二段|
|»»» payType|integer|true|none||支付类型 1:在线支付--全额现付 2：我要出票 3：申请出票 4：差额支付--部分现付 5：差额支付需审批|
|»»» diffCash|number|true|none||差额支付金额--单个人|
|»»» diffCashOrder|number|true|none||差额支付金额--订单|
|»»» paymentKind|string|true|none||下单支付类型  BALANCE(余额支付--对应一笔挂账)  CASH(全额支付--对应一笔现付)  DIFFCASH(差额支付--对应一笔挂账，一笔现付)|
|»»» productList|[object]|false|none||产品列表|
|»»»» name|string|false|none||姓名|
|»»»» certNo|string|false|none||证件|
|»»»» productType|string|false|none||产品类型|
|»»»» productTypeGroup|string|false|none||产品类型组|
|»»»» productMemo|string|false|none||产品描述|
|»»»» pretium|number|false|none||售价|
|»»»» productCount|number|false|none||数量|
|»»» nameList|[object]|false|none||乘机人列表|
|»»»» name|string|false|none||姓名|
|»»»» type|string|false|none||乘客类型|
|»»»» partnerName|string|false|none||同住人|
|»»»» certType|string|false|none||证件类型|
|»»»» certNo|string|false|none||证件号|
|»»»» coach|string|false|none||座位号|
|»»»» ticketNo|string|false|none||票号|
|»»» orderPlaneTgqList|[object]|true|none||退改签单列表|
|»»»» type|string|true|none||旅客类型|
|»»»» airId|string|true|none||航司代号|
|»»»» fromCity|string|true|none||出发城市|
|»»»» toCity|string|true|none||到达城市|
|»»»» cabin|string|true|none||舱位|
|»»»» discount|integer|true|none||折扣|
|»»»» flyDate|string|true|none||乘机日|
|»»»» receiveDate|string|true|none||确认日|
|»»»» refundRule|string|true|none||退票政策|
|»»»» changeRule|string|true|none||改期政策|
|»»»» issueRule|string|true|none||签转政策|
|»» approveUserList|[object]|false|none||审批人数据|
|»»» id|number|false|none||审批人ID|
|»»» name|string|false|none||姓名|
|»»» depName|string|false|none||部门|
|»»» depId|number|false|none||部门ID|
|»»» phone|string|false|none||手机|
|»»» email|string|false|none||邮箱|
|»»» tel|string|false|none||默认审批手机邮箱|
|»»» sameDepId|boolean|false|none||本部门|
|»»» approverGroupId|integer|false|none||审批人组id|
|»»» approveRank|number|false|none||审批顺序|
|»»» approveState|string|false|none||审批状态|
|»» travelPolicyList|[object]|false|none||订单差旅政策|
|»»» seq|number|true|none||对应原来的id|
|»»» policyJsonText|string|true|none||描述|
|»»» punish|string|true|none||处罚|
|»»» reason|string|true|none||原因|
|»»» remark|string|true|none||备注|
|»»» requireReason|boolean|true|none||必填|
|»»» policyValue|number|true|none||政策值|
|»»» type|integer|true|none||政策类型 ADVANCE_DAYS：未提前多少天出票  BOOKED：未预订前后____小时最低价   RIDE：最高乘坐（经济舱，高端经济舱，公务舱）航班    NOT_EXCEEDING_DISCOUNT：不允许超折扣   VIOLATION_APPLICATION：违反申请单匹配栏位   PLANELOWPRICE：预订本次航班低价   APPLICATION：申请单|
|»» citys|[object]|false|none||none|
|»»» cityCode|string|true|none||城市三字码|
|»»» cityName|string|true|none||城市名称|
|»»» airPortName|string|true|none||机场名称|
|»» airways|[object]|false|none||none|
|»»» companyNo|string|false|none||航空公司二字码|
|»»» companyName|string|false|none||航空公司简称|
|»»» fullCompanyName|string|false|none||航空公司全称|
|»» orderBasicDataJson|string|false|none||订单基本数据,提交机票支付需要|
|»» diffcashData|object|true|none||差额支付数据 订单有差额支付才返回此对象|
|»»» orderChoiceDiffPrice|boolean|true|none||客户下单选择差额支付  true(勾选差额支付),支付页面显示：差额付，全额付； false(不勾选差额支付)，支付页面显示：全挂账，差额付 ，全额付|
|»»» diffCashOrder|number|true|none||差额支付金额--订单 下单保存的差额支付|

## POST 获取客户余额 

POST /air/customer/clientBalance

一。arrearageNoselect与arrearageNoselectNew不一样，用红色显示arrearageNoselectNew

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 | empty object|none|

> 返回示例

> 200 Response

```json
{
  "tmsErrorCode": "string",
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": [
    {
      "creditLine": 0,
      "advance": 0,
      "advanceUse": 0,
      "arrearage": 0,
      "arrearageNoselect": 0,
      "avail": "string",
      "arrearageNoselectNew": 0
    }
  ]
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» tmsErrorCode|string|false|none||none|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|[object]|false|none||none|
|»» creditLine|number|true|none||授信额度|
|»» advance|number|true|none||预付款总额|
|»» advanceUse|number|true|none||已用预付款|
|»» arrearage|number|true|none||未付对帐金额|
|»» arrearageNoselect|number|true|none||未对帐金额|
|»» avail|string|true|none||可用余额 如后台没设置，显示：无限制；|
|»» arrearageNoselectNew|number|true|none||新系统未对帐金额|

## POST 机票支付--新订单 

POST /air/domestic/submitPlaneSendpki

说明：
notifyUrl，returnUrl参数说明
    productType：1（机票） 2（酒店） 3（火车） 4（用车） 6（旅游）7（火车需求单）
    browser： 0（PC） 1（APP）
一。
    a。支付宝接口提交网址为：[https://mapi\.alipay\.com/gateway\.do?\_input\_charset=utf\-8](https://mapi.alipay.com/gateway.do?_input_charset=utf-8)
    b。支付宝接口参数sign_type：MD5
二。微信支付
   a。公众号支付
      {
    "appId":"wx2421b1c4370ec43b",     //公众号名称，由商户传入
     "timeStamp":"1395712654",         //时间戳，自1970年以来的秒数
     "nonceStr":"e61463f8efa94090b1f366cccfbbb444", //随机串
     "package":"prepay_id=u802345jgfjsdfgsdg888",
     "signType":"MD5",         //微信签名方式：
     "paySign":"70EA570631E4BB79628FBCA90534C63FF7FADD89" //微信签名
      }
   **注意:如果**<span class="colour" style="color:rgb(85, 85, 85)">**get\_client\_basic\_data接口openid返回空，需要先调用**</span><span class="colour" style="color:rgba(13, 27, 62, 0.65)">**/air/domestic/getWxCode接口获取openid,支付的时候，openid需要传**</span>

b.新框架支付
   {
    appid    : "wx2421b1c4370ec43b",     //公众号名称，由商户传入
    partnerid: "1491846452",  //商户号
    prepayid : “sdfsdf678678”,  //预支付交易会话标识~~~~
    package  : package,
   noncestr : "e61463f8efa94090b1f366cccfbbb444", //随机串
   timestamp: "1395712654",         //时间戳，自1970年以来的秒数
   sign     : "sfsfd"  //签名
}
三。申请审批，差额支付需审批
      1。如果是多级审批，须传approverGroupId，approverId，mobile节点
      2。如果是单级审批，须传在approverList节点
四。paymentId是新支付接口用，需要跳转到
      [clientType](https://crmdev.feiheair.com/VuePage/hotel/index.html#/orderPay?payUnrealNo=250808093857A0189APF&clientType=PC&clientId=SZ002CTI&supplier)取值范围:

```
/**
 移动端浏览器页面
 */
H5,
/**
 * PC 浏览器
 */
PC,
/**
 * 手机 APP
 */
APP,
/**
 * 微信小程序
 */
WxMiniProgram,
/**
 * 公众号
 */
WechatMP,
```

    1.开发
       [https://crmdev.feiheair.com/VuePage/hotel/index.html#/orderPay?payUnrealNo=250808093857A0189APF&clientType=PC&clientId=SZ002CTI&supplier](https://crmdev.feiheair.com/VuePage/hotel/index.html#/orderPay?payUnrealNo=250808093857A0189APF&clientType=PC&clientId=SZ002CTI&supplier)

> Body 请求参数

```json
{
  "orderBasicDataJson": "string",
  "userSelectValue": 0,
  "mobile": "string",
  "approverGroupId": 0,
  "approverId": 0,
  "clientTravelPolicyReason": "string",
  "clientTravelPolicyReasonHasSelect": true,
  "payType": 0,
  "payTag": 0,
  "weixin": true,
  "newframe": true,
  "web": true,
  "openid": "string",
  "orderPriceList": [
    {
      "order_id": "string",
      "recPrice": 0,
      "payPrice": 0
    }
  ],
  "approverList": [
    {
      "approverId": 0,
      "mobile": "string"
    }
  ]
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» orderBasicDataJson|body|string| 是 ||订单基本数据 来自机票支付查询接口|
|» userSelectValue|body|integer| 否 ||用户选择 1:未变价提醒 2:变价提醒 4:审批人弹屏选择|
|» mobile|body|string| 否 ||审批人手机号或邮件 根据getTicketSendpki返回的smsApproval|
|» approverGroupId|body|integer| 是 ||审批人组ID 新加|
|» approverId|body|integer| 否 ||审批人ID|
|» clientTravelPolicyReason|body|string| 否 ||折扣差旅原因|
|» clientTravelPolicyReasonHasSelect|body|boolean| 否 ||差旅政策原因是否选择过 用户已经选择过，有可能不用输原因；没有选择过，须弹出画面让用户选择|
|» payType|body|integer| 是 ||支付类型 1:在线支付--全额现付 2：我要出票 3：申请出票 4：差额支付--部分现付 5：差额支付需审批|
|» payTag|body|integer| 否 ||支付方式 1：支付宝, 2：银联支付（废弃）,3:微信。注意：PayType为在线支付--全额现付,差额支付--部分现付，此参数为必填|
|» weixin|body|boolean| 否 ||公众号微信 openid为空时，此参数不能为true|
|» newframe|body|boolean| 否 ||新框架|
|» web|body|boolean| 否 ||是否PC网站发起|
|» openid|body|string| 否 ||weixin为true,此参数不能为空 公众号微信支付|
|» orderPriceList|body|[object]| 是 ||none|
|»» order_id|body|string| 是 ||订单号|
|»» recPrice|body|number| 是 ||应付款|
|»» payPrice|body|number| 是 ||已付款|
|» approverList|body|[object]| 否 ||审批人列表 单级审批允许传多个|
|»» approverId|body|integer| 是 ||审批人ID|
|»» mobile|body|string| 是 ||审批人手机号或邮件 根据getTicketSendpki返回的smsApproval|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "payType": 0,
    "violatePolicy": true,
    "showViolatePolicy": true,
    "transfer": true,
    "accoundBank": "string",
    "accoundName": "string",
    "accoundNo": "string",
    "pnrStatusIsDw": true,
    "payTimeout": "string",
    "canInvokeVerifyOrder": true,
    "order_idListForRt": [
      "string"
    ],
    "sendSucc": true,
    "userNeedSelectTravelPolicy": 0,
    "gotoOrderDetail": true,
    "oaApproveGotoUrl": "string",
    "alipayRequestData": {
      "ifApp": true,
      "partner": "string",
      "inputCharset": "string",
      "service": "string",
      "paymentType": "string",
      "notifyUrl": "string",
      "returnUrl": "string",
      "outTradeNo": "string",
      "subject": "string",
      "totalFee": "string",
      "sign": "string",
      "body": "string",
      "showUrl": "string",
      "paymentId": "string"
    },
    "wxpayRequestData": {
      "outTradeNo": "string",
      "totalFee": 0,
      "codeUrl": "string",
      "body": "string",
      "order_id": "string",
      "remainDate": "string",
      "sign": "string",
      "appId": "string",
      "timeStamp": "string",
      "nonceStr": "string",
      "packAge": "string",
      "signType": "string",
      "partnerid": "string",
      "prepayid": "string",
      "paymentId": "string"
    },
    "unionpayRequestData": {}
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» payType|number|false|none||支付类型 1:在线支付--全额现付 2：我要出票 3：申请出票 4：差额支付--部分现付 5：差额支付需审批|
|»» violatePolicy|boolean|false|none||违反折扣政策|
|»» showViolatePolicy|boolean|false|none||是否显示违反折扣政策|
|»» transfer|boolean|false|none||是否转帐|
|»» accoundBank|string|false|none||银行|
|»» accoundName|string|false|none||开户行|
|»» accoundNo|string|false|none||帐号|
|»» pnrStatusIsDw|boolean|false|none||Pnr特殊状态 pnr状态为DW不用rt,pat,需要提醒客户|
|»» payTimeout|string|false|none||不为空需要核价|
|»» canInvokeVerifyOrder|boolean|false|none||能否调用核价|
|»» order_idListForRt|[string]|false|none||核价订单号列表|
|»» sendSucc|boolean|false|none||发送成功|
|»» userNeedSelectTravelPolicy|number|false|none||需要选择差旅政策|
|»» gotoOrderDetail|boolean|false|none||需要跳转审批|
|»» oaApproveGotoUrl|string|false|none||OA审批跳转网址 此参数不为空，须调用getMultiOrderData接口获取订单数据，然后跳转到客户系统里  适用：3：申请出票|
|»» alipayRequestData|object|false|none||支付宝请求数据|
|»»» ifApp|boolean|true|none||是否app|
|»»» partner|string|true|none||商户，对应支付宝接口partner，seller_id参数|
|»»» inputCharset|string|true|none||编码，对应支付宝接口_input_charset参数|
|»»» service|string|true|none||服务，对应支付宝接口service参数|
|»»» paymentType|string|true|none||支付方式，对应支付宝接口payment_type参数|
|»»» notifyUrl|string|true|none||异步通知网址，对应支付宝接口notify_url参数|
|»»» returnUrl|string|true|none||同步通知网址，对应支付宝接口return_url参数|
|»»» outTradeNo|string|true|none||订单号，对应支付宝接口out_trade_no参数|
|»»» subject|string|true|none||订单名称，对应支付宝接口subject参数|
|»»» totalFee|string|true|none||付款金额，对应支付宝接口total_fee参数|
|»»» sign|string|true|none||签名，对应支付宝接口sign参数|
|»»» body|string|true|none||订单描述 pc需要，对应支付宝接口body参数|
|»»» showUrl|string|true|none||显示产品页面，对应支付宝接口show_url参数|
|»»» paymentId|string|true|none||支付流水号--新接口|
|»» wxpayRequestData|object|false|none||微信请求数据|
|»»» outTradeNo|string|true|none||订单号 获取微信支付状态需要 适用:pc扫码支付,新框架|
|»»» totalFee|number|true|none||付款金额 适用:pc扫码支付|
|»»» codeUrl|string|true|none||微信支付二维码地址 适用:pc扫码支付|
|»»» body|string|true|none||适用:pc扫码支付|
|»»» order_id|string|true|none||订单号 适用:pc扫码支付|
|»»» remainDate|string|true|none||剩余支付时间 超过时间需重新发起支付 适用:pc扫码支付|
|»»» sign|string|true|none||签名 适用:公众号,新框架|
|»»» appId|string|true|none||账号ID 适用:公众号,新框架|
|»»» timeStamp|string|true|none||时间戳 适用:公众号,新框架|
|»»» nonceStr|string|true|none||随机字符串 适用:公众号,新框架|
|»»» packAge|string|true|none||订单详情扩展字符串 适用:公众号,新框架 对应微信接口：package|
|»»» signType|string|true|none||签名方式 适用:公众号,新框架|
|»»» partnerid|string|true|none||商户号 适用:新框架|
|»»» prepayid|string|true|none||预支付交易会话标识 适用:新框架|
|»»» paymentId|string|true|none||支付流水号--新接口|
|»» unionpayRequestData|object|false|none||银联请求数据|

## POST 机票核价--新订单

POST /air/domestic/planeRtPat

> Body 请求参数

```json
{
  "order_id": "string",
  "operatorGroup": 0,
  "recPrice": 0
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» order_id|body|string| 是 ||订单号|
|» operatorGroup|body|integer| 否 ||操作组号|
|» recPrice|body|number| 否 ||应收款|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "succ": true,
    "result": "string",
    "orderSdProcessing": true,
    "recPrice": 0,
    "payPrice": 0,
    "pnrIsCancel": true,
    "showViolatePolicy": true,
    "hightFrequencyErrNames": "string"
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» succ|boolean|false|none||操作成功操作|
|»» result|string|false|none||结果|
|»» orderSdProcessing|boolean|true|none||订单订座处理中 true:正在占座，请稍等 mub2t适用|
|»» recPrice|number|false|none||应付款|
|»» payPrice|number|false|none||已付款|
|»» pnrIsCancel|boolean|false|none||pnr是否取消了|
|»» showViolatePolicy|boolean|false|none||是否显示违反折扣政策|
|»» hightFrequencyErrNames|string|true|none||非白名单姓名列表  张三,李四|

## POST 我的机票订单

POST /air/domestic/myselfTicketOrder

一。pageNo为1时，才计算totalPage,total
二。关联状态列表
      a\.选择全部：RESERVED:预留中\,WAITE\_APPROVAL:待审批\,APPROVAL\_REJECT:审批拒绝\,IN\_ISSUING\_TICKETS:出票中\,HAS\_ISSUING\_TICKET:出票成功\,IN\_REFUND\_CHANGE:退改中\,HAS\_REFUND\_CHANGE:退改成功\,CANCEL:已取消
      b\.选择订票单\.：RESERVED:预留中\,WAITE\_APPROVAL:待审批\,APPROVAL\_REJECT:审批拒绝\,IN\_ISSUING\_TICKETS:出票中\,HAS\_ISSUING\_TICKET:出票成功\,CANCEL:已取消
      c\.选择退改单：RESERVED:预留中\,WAITE\_APPROVAL:待审批\,APPROVAL\_REJECT:审批拒绝\,IN\_REFUND\_CHANGE:退改中\,HAS\_REFUND\_CHANGE:退改成功\,CANCEL:已取消

> Body 请求参数

```json
{
  "productType": 0,
  "state": "string",
  "dateType": 0,
  "startDate": "string",
  "endDate": "string",
  "frCity": "string",
  "toCity": "string",
  "nameType": 0,
  "name": "string",
  "order_id": "string",
  "pageNo": 0,
  "pageSize": 0
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» productType|body|integer| 是 ||产品类型 0:全部 1:订票 2:退改|
|» state|body|string| 是 ||状态：RESERVED:预留中,WAITE_APPROVAL:待审批,APPROVAL_REJECT:审批拒绝,IN_ISSUING_TICKETS:出票中,HAS_ISSUING_TICKET:出票成功,IN_REFUND_CHANGE:退改中,HAS_REFUND_CHANGE:退改成功,CANCEL:已取消，WAITPAY:待支付|
|» dateType|body|integer| 是 ||日期类型 0:下单日 1:乘机日|
|» startDate|body|string| 是 ||开始日期   2020-01-01|
|» endDate|body|string| 是 ||结束日期 2020-01-01|
|» frCity|body|string| 是 ||出发城市三字码 例:SZX|
|» toCity|body|string| 是 ||到达城市三字码 例:PEK|
|» nameType|body|integer| 是 ||姓名类型 0:乘机人 1:审批人|
|» name|body|string| 是 ||姓名|
|» order_id|body|string| 是 ||订单号 指定此条件,日期不管制|
|» pageNo|body|integer| 是 ||页码|
|» pageSize|body|integer| 是 ||页大小|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "dataList": [
      {
        "state": "string",
        "order_id": "string",
        "orderTypeCode": 0,
        "productTypeCode": 0,
        "createDate": "string",
        "productMemo": "string",
        "returnMemo": "string",
        "noadvanceReason_web": "string",
        "price": 0,
        "changePrice": 0,
        "upgradePrice": 0,
        "creturnFee": 0,
        "recPrice": 0,
        "public_web": "string",
        "payTypes": "string",
        "operateType": "string",
        "hasReply": true,
        "replyIsDeny": true,
        "refuse": "string",
        "names": [
          "string"
        ],
        "approvers": [
          {
            "approverGroupId": null,
            "rank": null,
            "state": null,
            "approver": null,
            "rejectReason": null
          }
        ],
        "transferFlight": true
      }
    ],
    "totalPage": 0,
    "pageNo": 0,
    "pageSize": 0,
    "total": 0,
    "haveNextPage": true
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» dataList|[object]|false|none||none|
|»»» state|string|true|none||状态|
|»»» order_id|string|true|none||订单号|
|»»» orderTypeCode|number|true|none||订单类型 0：正常 1:退货 2:改签|
|»»» productTypeCode|number|true|none||产品类型 1:国内机票 2:国际机票 3:国内酒店 4:国际酒店 5:火车票 6:用车|
|»»» createDate|string|true|none||创建日期|
|»»» productMemo|string|true|none||产品描述|
|»»» returnMemo|string|true|none||退改类型|
|»»» noadvanceReason_web|string|true|none||事由|
|»»» price|number|true|none||单价|
|»»» changePrice|number|true|none||改签费|
|»»» upgradePrice|number|true|none||升舱费|
|»»» creturnFee|number|true|none||退票费|
|»»» recPrice|number|true|none||应收款|
|»»» public_web|string|true|none||公费自费 1：公费|
|»»» payTypes|string|true|none||付款类型列表 挂账,面付,现付|
|»»» operateType|string|true|none||操作类型 一。正常单:1.预留中:支付出票，我要出票，申请出票; 2.待审批：审批，催促审批   二。改签单:1.预留中:支付改签，我要改签，申请改签;2.待审批：审批，催促审批  三。退货单:1.预留中:我要退票，申请退票;2.待审批：审批，催促审批|
|»»» hasReply|boolean|true|none||是否回复|
|»»» replyIsDeny|boolean|true|none||回复是否拒绝 ：通过/拒绝|
|»»» refuse|string|true|none||拒绝原因|
|»»» names|[string]|true|none||乘机人列表|
|»»» approvers|[object]|true|none||none|
|»»»» approverGroupId|integer|true|none||审批人组id >0就是多级审批|
|»»»» rank|integer|true|none||none|
|»»»» state|string|true|none||none|
|»»»» approver|string|true|none||none|
|»»»» rejectReason|string|true|none||none|
|»»» transferFlight|boolean|true|none||中转航班|
|»» totalPage|number|false|none||总共页数|
|»» pageNo|number|false|none||当前页|
|»» pageSize|number|false|none||每页显示条数|
|»» total|number|false|none||总共行数|
|»» haveNextPage|boolean|false|none||是否存在下一页|

## POST 取消机票

POST /air/domestic/cancelTicketOrder

> Body 请求参数

```json
{
  "order_id": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|Content-Type|header|string| 是 ||none|
|token|header|string| 否 ||none|
|body|body|object| 否 ||none|
|» order_id|body|string| 是 ||订单号|

> 返回示例

> 200 Response

```json
{
  "errorCode": "string",
  "errorMsg": "string",
  "requestSeqNo": "string",
  "data": {
    "orderMsg": "string",
    "pnrMsg": "string",
    "updateTime": "string"
  }
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### 返回数据结构

状态码 **200**

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» errorCode|string|false|none||none|
|» errorMsg|string|false|none||none|
|» requestSeqNo|string|false|none||none|
|» data|object|false|none||none|
|»» orderMsg|string|false|none||订单信息|
|»» pnrMsg|string|false|none||pnr信息|
|»» updateTime|string|false|none||订单修改时间|

# 数据模型

