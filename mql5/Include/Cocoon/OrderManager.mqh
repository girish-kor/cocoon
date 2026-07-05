//+------------------------------------------------------------------+
//| OrderManager.mqh  —  order execution for the Cocoon EA           |
//| DOCUMENT.md §9.4, §9.5, §13.3. Idempotency-key dedup on the EA   |
//| side mirrors the Python IdempotencyCache so an ambiguous network |
//| retry never produces a duplicate OrderSend.                      |
//+------------------------------------------------------------------+
#ifndef COCOON_ORDER_MANAGER_MQH
#define COCOON_ORDER_MANAGER_MQH

#include <Trade/Trade.mqh>
#include "Protocol.mqh"

class CCocoonOrderManager
  {
private:
   CTrade            m_trade;
   string            m_seen_keys[];   // recently-processed idempotency keys
   long              m_seen_tickets[];
   int               m_ttl_count;

   int               FindKey(const string key)
     {
      for(int i=0;i<ArraySize(m_seen_keys);i++)
         if(m_seen_keys[i]==key)
            return i;
      return -1;
     }

   void              RememberKey(const string key,const long ticket)
     {
      int n=ArraySize(m_seen_keys);
      ArrayResize(m_seen_keys,n+1);
      ArrayResize(m_seen_tickets,n+1);
      m_seen_keys[n]=key;
      m_seen_tickets[n]=ticket;
     }

public:
   void              Init(const long magic)
     {
      m_trade.SetExpertMagicNumber(magic);
      m_ttl_count=256;
     }

   //--- Returns an OrderResultPayload; idempotent on idempotency_key.
   OrderResultPayload Submit(const OrderSubmitPayload &req)
     {
      OrderResultPayload res;
      res.idempotency_key=req.idempotency_key;
      res.filled_volume_lots=0.0;
      res.filled_price=0.0;
      res.reject_reason="";

      int seen=FindKey(req.idempotency_key);
      if(seen>=0)
        {
         res.status=STATUS_ACKNOWLEDGED;
         res.broker_ticket_id=m_seen_tickets[seen];
         return res;
        }

      bool ok=false;
      if(req.direction=="BUY")
         ok=m_trade.Buy(req.volume_lots,req.symbol,0.0,req.stop_loss_price,req.take_profit_price);
      else
         ok=m_trade.Sell(req.volume_lots,req.symbol,0.0,req.stop_loss_price,req.take_profit_price);

      if(ok && m_trade.ResultRetcode()==TRADE_RETCODE_DONE)
        {
         long ticket=(long)m_trade.ResultOrder();
         res.status=STATUS_FILLED;
         res.broker_ticket_id=ticket;
         res.filled_volume_lots=m_trade.ResultVolume();
         res.filled_price=m_trade.ResultPrice();
         RememberKey(req.idempotency_key,ticket);
        }
      else
        {
         res.status=STATUS_REJECTED_BY_BROKER;
         res.broker_ticket_id=-1;
         res.reject_reason=m_trade.ResultRetcodeDescription();
        }
      return res;
     }

   OrderResultPayload Cancel(const long ticket)
     {
      OrderResultPayload res;
      res.idempotency_key="";
      bool ok=m_trade.PositionClose(ticket);
      res.status=ok?STATUS_FILLED:STATUS_REJECTED_BY_BROKER;
      res.broker_ticket_id=ticket;
      res.filled_volume_lots=0.0;
      res.filled_price=0.0;
      res.reject_reason=ok?"":m_trade.ResultRetcodeDescription();
      return res;
     }

   OrderResultPayload Modify(const long ticket,const double sl,const double tp)
     {
      OrderResultPayload res;
      res.idempotency_key="";
      bool ok=m_trade.PositionModify(ticket,sl,tp);
      res.status=ok?STATUS_ACKNOWLEDGED:STATUS_REJECTED_BY_BROKER;
      res.broker_ticket_id=ticket;
      res.reject_reason=ok?"":m_trade.ResultRetcodeDescription();
      return res;
     }
  };

#endif // COCOON_ORDER_MANAGER_MQH
//+------------------------------------------------------------------+
