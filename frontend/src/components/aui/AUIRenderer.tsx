import type { CardDescriptor } from '../../types';
import { FormCard } from './cards/FormCard';
import { SelectionListCard } from './cards/SelectionListCard';
import { FlightResultCard } from './cards/FlightResultCard';
import { PriceVerifyCard } from './cards/PriceVerifyCard';
import { PolicyDecisionCard } from './cards/PolicyDecisionCard';
import { OrderConfirmCard } from './cards/OrderConfirmCard';
import { OrderSuccessCard } from './cards/OrderSuccessCard';
import { CannotOrderCard } from './cards/CannotOrderCard';
import { ChatFallbackCard } from './cards/ChatFallbackCard';
import { QuestionCard } from './cards/QuestionCard';
import { TodoListCard } from './cards/TodoListCard';
import { DomesticAguiCard } from './cards/DomesticAguiCard';
import { hasDomesticAgui } from './cards/domesticAgui';
import { CardShell } from './CardShell';

export interface AUIRendererProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// Dispatcher for the 11+ AUIP card types.  Cards never make HTTP calls
// themselves - every submission flows through `onSubmit` so the parent
// hook can route it to the right `/agent/turn/{id}/resume` call.
export function AUIRenderer({ card, suspended, submitted, onSubmit }: AUIRendererProps) {
  if (hasDomesticAgui(card)) {
    return (
      <DomesticAguiCard
        card={card}
        suspended={suspended}
        submitted={submitted}
        onSubmit={onSubmit}
      />
    );
  }

  switch (card.card_type) {
    case 'OD_INPUT':
    case 'PASSENGER_FORM':
    case 'OAT_BINDING':
      return (
        <FormCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'FLIGHT_RESULT':
      return (
        <FlightResultCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'FLIGHT_LIST':
    case 'CABIN_LIST':
      return (
        <SelectionListCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'PRICE_VERIFY':
      return (
        <PriceVerifyCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'POLICY_DECISION':
      return (
        <PolicyDecisionCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'ORDER_CONFIRM':
      return (
        <OrderConfirmCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'ORDER_SUCCESS':
      return (
        <OrderSuccessCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'CANNOT_ORDER':
      return (
        <CannotOrderCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'CHAT_FALLBACK':
      return (
        <ChatFallbackCard
          card={card}
          suspended={suspended}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    // P7: opencode 原生 question / todo (一般不通过 AUIRenderer 走,
    // 父组件从 ChatMessage.pendingQuestion/todoView 直接渲染; 这里
    // 仅兜底 — 例如未来 ask_user 拦截器能直接产生 QUESTION card 时)
    case 'QUESTION':
      return (
        <QuestionCard
          card={card}
          suspended={suspended}
          submitted={submitted}
        />
      );
    case 'TODO_LIST':
      return (
        <TodoListCard
          card={card}
          suspended={suspended}
          submitted={submitted}
        />
      );
    default:
      return (
        <CardShell
          card={card}
          suspended={suspended}
          submitted={submitted}
        >
          <p className="aui-card-message">
            Unknown card type: <code>{String(card.card_type)}</code>
          </p>
        </CardShell>
      );
  }
}
