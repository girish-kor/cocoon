//+------------------------------------------------------------------+
//| HeartbeatManager.mqh  —  EA-side heartbeat emitter                |
//| DOCUMENT.md §13.4. Publishes HEARTBEAT on the PUB channel every  |
//| heartbeat_interval_ms; the Python Broker Adapter counts misses.  |
//+------------------------------------------------------------------+
#ifndef COCOON_HEARTBEAT_MANAGER_MQH
#define COCOON_HEARTBEAT_MANAGER_MQH

class CCocoonHeartbeat
  {
private:
   ulong             m_interval_ms;
   ulong             m_last_sent_ms;

public:
   void              Init(const ulong interval_ms)
     {
      m_interval_ms=interval_ms;
      m_last_sent_ms=0;
     }

   //--- Returns true when a heartbeat is due (caller then PUBs it).
   bool              Due()
     {
      ulong now=(ulong)GetTickCount64();
      if(now-m_last_sent_ms>=m_interval_ms)
        {
         m_last_sent_ms=now;
         return true;
        }
      return false;
     }

   ulong             NowUnixMs()
     {
      return (ulong)(TimeGMT()*1000);
     }
  };

#endif // COCOON_HEARTBEAT_MANAGER_MQH
//+------------------------------------------------------------------+
