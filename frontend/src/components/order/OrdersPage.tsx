import { useState } from 'react';
import type { Order } from '../../types';
import { OrderCard, Tabs } from './index';
import { OrderDetail } from './OrderDetail';
import { ConfirmModal, Empty } from '../common';
import './OrdersPage.css';

const mockOrders: Order[] = [
  {
    id: '1',
    orderNo: 'TX20260529001',
    status: 'pending',
    flights: [{
      id: 'f1',
      airline: '中国国际航空',
      airlineCode: 'CA',
      flightNumber: 'CA1234',
      departure: { city: '北京', airport: '首都国际机场', airportCode: 'PEK', time: '08:30', date: '2026-06-01' },
      arrival: { city: '上海', airport: '浦东国际机场', airportCode: 'PVG', time: '10:45', date: '2026-06-01' },
      duration: '2小时15分钟',
      cabinClass: 'economy',
      price: 860,
      tax: 50,
      remainingSeats: 28,
      aircraft: '波音737-800'
    }],
    passengers: [{ name: '张三', type: 'adult', idType: '身份证', idNumber: '110101199001011234' }],
    totalPrice: 910,
    tax: 50,
    createdAt: '2026-05-29 10:00:00',
    travelDate: '2026-06-01'
  },
  {
    id: '2',
    orderNo: 'TX20260528002',
    status: 'confirmed',
    flights: [{
      id: 'f2',
      airline: '东方航空',
      airlineCode: 'MU',
      flightNumber: 'MU5678',
      departure: { city: '上海', airport: '浦东国际机场', airportCode: 'PVG', time: '14:00', date: '2026-06-05' },
      arrival: { city: '北京', airport: '首都国际机场', airportCode: 'PEK', time: '16:15', date: '2026-06-05' },
      duration: '2小时15分钟',
      cabinClass: 'economy',
      price: 780,
      tax: 50,
      remainingSeats: 20,
      aircraft: '空客A320'
    }],
    passengers: [
      { name: '张三', type: 'adult', idType: '身份证', idNumber: '110101199001011234' },
      { name: '李四', type: 'adult', idType: '身份证', idNumber: '110101199002022345' }
    ],
    totalPrice: 1660,
    tax: 100,
    createdAt: '2026-05-28 15:30:00',
    paidAt: '2026-05-28 15:35:00',
    travelDate: '2026-06-05'
  },
  {
    id: '3',
    orderNo: 'TX20260520003',
    status: 'completed',
    flights: [{
      id: 'f3',
      airline: '南方航空',
      airlineCode: 'CZ',
      flightNumber: 'CZ9012',
      departure: { city: '北京', airport: '大兴国际机场', airportCode: 'PKX', time: '09:00', date: '2026-05-20' },
      arrival: { city: '广州', airport: '白云国际机场', airportCode: 'CAN', time: '12:00', date: '2026-05-20' },
      duration: '3小时',
      cabinClass: 'business',
      price: 2180,
      tax: 80,
      remainingSeats: 12,
      aircraft: '波音787-9'
    }],
    passengers: [{ name: '王五', type: 'adult', idType: '身份证', idNumber: '110101198505053456' }],
    totalPrice: 2260,
    tax: 80,
    createdAt: '2026-05-20 08:00:00',
    paidAt: '2026-05-20 08:05:00',
    travelDate: '2026-05-20'
  }
];

const tabs = [
  { id: 'pending', label: '待支付', count: 1 },
  { id: 'confirmed', label: '待出行', count: 1 },
  { id: 'completed', label: '已完成', count: 1 },
  { id: 'all', label: '全部' }
];

export function OrdersPage({ onAskAI }: { onAskAI?: (prompt: string) => void } = {}) {
  const [activeTab, setActiveTab] = useState('pending');
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [cancelOrder, setCancelOrder] = useState<Order | null>(null);

  const filteredOrders = activeTab === 'all'
    ? mockOrders
    : mockOrders.filter((o) => o.status === activeTab);

  const handlePay = (order: Order) => {
    // 后端尚未提供 pay 接口；通过 AI 助手发起支付意图。
    onAskAI?.(`帮我支付订单 ${order.orderNo}`);
  };

  const handleCancel = (order: Order) => {
    setCancelOrder(order);
  };

  const handleView = (order: Order) => {
    setSelectedOrder(order);
    setShowDetail(true);
  };

  const confirmCancel = () => {
    if (cancelOrder) {
      // 后端尚未提供 cancel 接口；通过 AI 助手发起取消意图。
      onAskAI?.(`帮我取消订单 ${cancelOrder.orderNo}`);
      setCancelOrder(null);
    }
  };

  return (
    <div className="orders-page">
      <div className="orders-header">
        <h1>我的订单</h1>
        <p className="orders-subtitle">当前展示为示例数据；点击「去支付/取消」会唤起 AI 助手代为操作。</p>
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab}>
        <div className="orders-list">
          {filteredOrders.length > 0 ? (
            filteredOrders.map((order, index) => (
              <div
                key={order.id}
                className="order-card-wrapper"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <OrderCard
                  order={order}
                  onPay={handlePay}
                  onCancel={handleCancel}
                  onView={handleView}
                />
              </div>
            ))
          ) : (
            <Empty
              title="暂无订单"
              description={getEmptyDescription(activeTab)}
              action={
                onAskAI
                  ? { label: '问问 AI 助手', onClick: () => onAskAI('我想预订机票') }
                  : undefined
              }
            />
          )}
        </div>
      </Tabs>

      <OrderDetail
        order={selectedOrder}
        open={showDetail}
        onClose={() => setShowDetail(false)}
        onPay={handlePay}
        onCancel={handleCancel}
      />

      <ConfirmModal
        open={!!cancelOrder}
        onClose={() => setCancelOrder(null)}
        onConfirm={confirmCancel}
        title="取消订单"
        message={
          cancelOrder
            ? `确定要取消订单 ${cancelOrder.orderNo} 吗？该操作将通过 AI 助手发起。`
            : ''
        }
        confirmText="确定取消"
        cancelText="返回"
        variant="danger"
      />
    </div>
  );
}

function getEmptyDescription(tab: string): string {
  switch (tab) {
    case 'pending':
      return '您没有待支付的订单';
    case 'confirmed':
      return '您没有即将出行的订单';
    case 'completed':
      return '您没有已完成的订单';
    default:
      return '您还没有任何订单';
  }
}
