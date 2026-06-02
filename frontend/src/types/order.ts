import type { Flight } from './flight';

export type OrderStatus = 'pending' | 'paid' | 'confirmed' | 'completed' | 'cancelled' | 'refunded';

export interface Passenger {
  name: string;
  type: 'adult' | 'child' | 'infant';
  idType: string;
  idNumber: string;
}

export interface Order {
  id: string;
  orderNo: string;
  status: OrderStatus;
  flights: Flight[];
  passengers: Passenger[];
  totalPrice: number;
  tax: number;
  createdAt: string;
  paidAt?: string;
  travelDate: string;
  violation?: {
    type: string;
    amount: number;
    description: string;
  };
}
