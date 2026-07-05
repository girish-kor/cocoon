//+------------------------------------------------------------------+
//| Protocol.mqh  —  Cocoon MT5 bridge wire protocol                 |
//| Mirrors src/cocoon/bridge/protocol.py (DOCUMENT.md §13).          |
//| msgpack envelope: { v, type, ts, session_id, payload }.          |
//+------------------------------------------------------------------+
#ifndef COCOON_PROTOCOL_MQH
#define COCOON_PROTOCOL_MQH

#define COCOON_PROTOCOL_VERSION 1

// Message type strings — must match MessageType in protocol.py exactly.
#define MSG_HELLO            "HELLO"
#define MSG_ACK              "ACK"
#define MSG_HEARTBEAT        "HEARTBEAT"
#define MSG_BAR_CLOSED       "BAR_CLOSED"
#define MSG_TICK             "TICK"
#define MSG_ORDER_SUBMIT     "ORDER_SUBMIT"
#define MSG_ORDER_RESULT     "ORDER_RESULT"
#define MSG_ORDER_CANCEL     "ORDER_CANCEL"
#define MSG_ORDER_MODIFY     "ORDER_MODIFY"
#define MSG_POSITIONS_QUERY  "POSITIONS_QUERY"
#define MSG_POSITIONS_RESULT "POSITIONS_RESULT"
#define MSG_ORDERS_QUERY     "ORDERS_QUERY"
#define MSG_ORDERS_RESULT    "ORDERS_RESULT"
#define MSG_ERROR            "ERROR"

// Order status strings — must match OrderStatus in core/interfaces.
#define STATUS_ACKNOWLEDGED      "ACKNOWLEDGED"
#define STATUS_FILLED            "FILLED"
#define STATUS_PARTIALLY_FILLED  "PARTIALLY_FILLED"
#define STATUS_REJECTED_BY_BROKER "REJECTED_BY_BROKER"

//--- ORDER_SUBMIT payload (Python -> EA), §13.3
struct OrderSubmitPayload
  {
   string            idempotency_key;
   string            symbol;
   string            direction;        // "BUY" | "SELL"
   double            volume_lots;
   double            stop_loss_price;
   double            take_profit_price;
   double            max_slippage_pips;
  };

//--- ORDER_RESULT payload (EA -> Python), §13.3
struct OrderResultPayload
  {
   string            idempotency_key;
   string            status;
   long              broker_ticket_id; // -1 == null
   double            filled_volume_lots;
   double            filled_price;
   string            reject_reason;
  };

//--- BAR_CLOSED payload (EA -> Python, PUB)
struct BarClosedPayload
  {
   string            symbol;
   string            timeframe;
   double            open;
   double            high;
   double            low;
   double            close;
   double            volume;
  };

#endif // COCOON_PROTOCOL_MQH
//+------------------------------------------------------------------+
