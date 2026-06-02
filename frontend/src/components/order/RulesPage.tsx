import './RulesPage.css';

interface Rule {
  category: string;
  icon: React.ReactNode;
  items: { title: string; content: string }[];
}

const rules: Rule[] = [
  {
    category: '机票',
    icon: <AirplaneIcon />,
    items: [
      { title: '国内机票', content: '经济舱机票价格上限为全价票的75折；商务舱价格上限为经济舱全价的3倍。' },
      { title: '国际机票', content: '需提前7天以上预订，且需提供出差审批证明。' },
      { title: '违规情况', content: '超出差标部分由员工个人承担，系统将标记为违规记录。' }
    ]
  },
  {
    category: '火车票',
    icon: <TrainIcon />,
    items: [
      { title: '二等座', content: '高铁二等座可全额报销。' },
      { title: '一等座', content: '仅限长途出差（一等座与二等座差价不超过100元）可报销。' }
    ]
  },
  {
    category: '酒店',
    icon: <HotelIcon />,
    items: [
      { title: '一线城市', content: '北京、上海、广州、深圳：单晚上限500元。' },
      { title: '其他城市', content: '其他城市：单晚上限350元。' }
    ]
  }
];

export function RulesPage() {
  return (
    <div className="rules-page">
      <div className="rules-header">
        <h1>差旅规则</h1>
        <p>了解公司差旅费用标准，合理规划出行</p>
      </div>

      <div className="rules-list">
        {rules.map((rule) => (
          <div key={rule.category} className="rule-category">
            <div className="rule-category-header">
              <span className="rule-icon">{rule.icon}</span>
              <h2>{rule.category}</h2>
            </div>
            <div className="rule-items">
              {rule.items.map((item, idx) => (
                <div key={idx} className="rule-item">
                  <h3>{item.title}</h3>
                  <p>{item.content}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AirplaneIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}

function TrainIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="3" width="16" height="14" rx="2" />
      <path d="M4 11h16" />
      <path d="M12 3v8" />
      <path d="M8 19l-2 3" />
      <path d="M16 19l2 3" />
    </svg>
  );
}

function HotelIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 21h18" />
      <path d="M5 21V7l8-4 8 4v14" />
      <path d="M9 21v-6h6v6" />
    </svg>
  );
}
