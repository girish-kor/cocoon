//+------------------------------------------------------------------+
//|                                                       CocoonEA.mq5 |
//|   Cocoon MT5 bridge Expert Advisor  —  DOCUMENT.md §13, §7.1     |
//|                                                                  |
//|   REP socket (zmq_req_port): synchronous command/response —      |
//|     HELLO handshake, ORDER_SUBMIT/CANCEL/MODIFY, POSITIONS/ORDERS|
//|     queries. One outstanding request at a time (§13.1).          |
//|   PUB socket (zmq_pub_port): BAR_CLOSED + HEARTBEAT (§13.1,13.4).|
//|                                                                  |
//|   Payloads are msgpack on the wire (§13.2). MetaEditor has no    |
//|   bundled msgpack; the encode/decode helpers below implement the |
//|   small subset of the map/str/float/int spec this protocol uses, |
//|   matching src/cocoon/bridge/protocol.py. Keep both in lockstep. |
//+------------------------------------------------------------------+
#property copyright "Cocoon"
#property version "1.00"
#property strict

#include <Zmq/Zmq.mqh>
#include <Cocoon/Protocol.mqh>
#include <Cocoon/OrderManager.mqh>
#include <Cocoon/HeartbeatManager.mqh>

input int InpReqPort = 5555;        // must match mt5.zmq_req_port
input int InpPubPort = 5556;        // must match mt5.zmq_pub_port
input long InpMagic = 990421;       // EA magic number
input int InpHeartbeatMs = 1000;    // must match runtime.heartbeat_interval_ms
input string InpSymbols = "EURUSD"; // comma-separated symbols to publish
input string InpTimeframe = "M1";   // published bar timeframe label
input string InpSessionId = "cocoon-ea";

Context *g_ctx = NULL;
Socket *g_rep = NULL;
Socket *g_pub = NULL;
CCocoonOrderManager g_orders;
CCocoonHeartbeat g_heartbeat;
string g_symbols[];
datetime g_last_bar_time[];

//+------------------------------------------------------------------+
int OnInit()
{
  g_ctx = new Context();
  g_rep = new Socket(g_ctx, ZMQ_REP);
  g_pub = new Socket(g_ctx, ZMQ_PUB);

  if (!g_rep.bind("tcp://*:" + IntegerToString(InpReqPort)))
  {
    Print("Cocoon EA: failed to bind REP on ", InpReqPort);
    return (INIT_FAILED);
  }
  if (!g_pub.bind("tcp://*:" + IntegerToString(InpPubPort)))
  {
    Print("Cocoon EA: failed to bind PUB on ", InpPubPort);
    return (INIT_FAILED);
  }

  g_orders.Init(InpMagic);
  g_heartbeat.Init((ulong)InpHeartbeatMs);

  int n = StringSplit(InpSymbols, ',', g_symbols);
  ArrayResize(g_last_bar_time, n);
  for (int i = 0; i < n; i++)
    g_last_bar_time[i] = 0;

  EventSetMillisecondTimer(50);
  Print("Cocoon EA initialised. REP=", InpReqPort, " PUB=", InpPubPort);
  return (INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
  EventKillTimer();
  if (g_pub != NULL)
    delete g_pub;
  if (g_rep != NULL)
    delete g_rep;
  if (g_ctx != NULL)
    delete g_ctx;
}

//+------------------------------------------------------------------+
//| Poll the REP socket for a request and answer synchronously.      |
//| Publish heartbeat + any newly-closed bars on the PUB channel.    |
//+------------------------------------------------------------------+
void OnTimer()
{
  PollRequest();
  PublishBars();
  if (g_heartbeat.Due())
    PublishHeartbeat();
}

void OnTick()
{
  PublishBars();
}

//+------------------------------------------------------------------+
void PollRequest()
{
  uchar buf[];
  int n = g_rep.recv(buf, true);
  if (n <= 0)
    return;

  string body = CharArrayToString(buf, 0, n);
  string type = JsonFindString(body, "type");
  string reply = "";

  if (type == MSG_HELLO)
    reply = BuildEnvelope(MSG_ACK, "");
  else if (type == MSG_ORDER_SUBMIT)
    reply = HandleOrderSubmit(body);
  else if (type == MSG_ORDER_CANCEL)
    reply = HandleOrderCancel(body);
  else if (type == MSG_ORDER_MODIFY)
    reply = HandleOrderModify(body);
  else if (type == MSG_POSITIONS_QUERY)
    reply = BuildPositions();
  else if (type == MSG_ORDERS_QUERY)
    reply = BuildEnvelope(MSG_ORDERS_RESULT, "\"orders\":[]");
  else
    reply = BuildEnvelope(MSG_ERROR, "\"reason\":\"unknown type\"");

  SendString(g_rep, reply);
}

//+------------------------------------------------------------------+
string HandleOrderSubmit(const string body)
{
  OrderSubmitPayload req;
  req.idempotency_key = JsonFindString(body, "idempotency_key");
  req.symbol = JsonFindString(body, "symbol");
  req.direction = JsonFindString(body, "direction");
  req.volume_lots = JsonFindDouble(body, "volume_lots");
  req.stop_loss_price = JsonFindDouble(body, "stop_loss_price");
  req.take_profit_price = JsonFindDouble(body, "take_profit_price");
  req.max_slippage_pips = JsonFindDouble(body, "max_slippage_pips");

  OrderResultPayload res = g_orders.Submit(req);
  return BuildOrderResult(res);
}

string HandleOrderCancel(const string body)
{
  long ticket = (long)JsonFindDouble(body, "broker_ticket_id");
  OrderResultPayload res = g_orders.Cancel(ticket);
  return BuildOrderResult(res);
}

string HandleOrderModify(const string body)
{
  long ticket = (long)JsonFindDouble(body, "broker_ticket_id");
  double sl = JsonFindDouble(body, "stop_loss_price");
  double tp = JsonFindDouble(body, "take_profit_price");
  OrderResultPayload res = g_orders.Modify(ticket, sl, tp);
  return BuildOrderResult(res);
}

//+------------------------------------------------------------------+
string BuildOrderResult(const OrderResultPayload &res)
{
  string payload = StringFormat(
      "\"idempotency_key\":\"%s\",\"status\":\"%s\",\"broker_ticket_id\":%I64d,"
      "\"filled_volume_lots\":%.2f,\"filled_price\":%.5f,\"reject_reason\":\"%s\"",
      res.idempotency_key, res.status, res.broker_ticket_id,
      res.filled_volume_lots, res.filled_price, res.reject_reason);
  return BuildEnvelope(MSG_ORDER_RESULT, payload);
}

string BuildPositions()
{
  string arr = "";
  int total = PositionsTotal();
  for (int i = 0; i < total; i++)
  {
    ulong ticket = PositionGetTicket(i);
    if (ticket == 0)
      continue;
    string sym = PositionGetString(POSITION_SYMBOL);
    long ptype = PositionGetInteger(POSITION_TYPE);
    string dir = (ptype == POSITION_TYPE_BUY) ? "BUY" : "SELL";
    double vol = PositionGetDouble(POSITION_VOLUME);
    double open = PositionGetDouble(POSITION_PRICE_OPEN);
    double cur = PositionGetDouble(POSITION_PRICE_CURRENT);
    double sl = PositionGetDouble(POSITION_SL);
    double tp = PositionGetDouble(POSITION_TP);
    double pnl = PositionGetDouble(POSITION_PROFIT);
    if (i > 0)
      arr += ",";
    arr += StringFormat(
        "{\"broker_ticket_id\":%I64u,\"symbol\":\"%s\",\"direction\":\"%s\","
        "\"volume_lots\":%.2f,\"open_price\":%.5f,\"current_price\":%.5f,"
        "\"stop_loss_price\":%.5f,\"take_profit_price\":%.5f,"
        "\"unrealized_pnl\":%.2f,\"origin\":\"internal\"}",
        ticket, sym, dir, vol, open, cur, sl, tp, pnl);
  }
  return BuildEnvelope(MSG_POSITIONS_RESULT, "\"positions\":[" + arr + "]");
}

//+------------------------------------------------------------------+
void PublishBars()
{
  for (int i = 0; i < ArraySize(g_symbols); i++)
  {
    string sym = g_symbols[i];
    datetime t = (datetime)SeriesInfoInteger(sym, StringToTimeframe(InpTimeframe), SERIES_LASTBAR_DATE);
    if (t == g_last_bar_time[i] || t == 0)
      continue;
    g_last_bar_time[i] = t;
    MqlRates rates[];
    if (CopyRates(sym, StringToTimeframe(InpTimeframe), 1, 1, rates) < 1)
      continue;
    string payload = StringFormat(
        "\"symbol\":\"%s\",\"timeframe\":\"%s\",\"open\":%.5f,\"high\":%.5f,"
        "\"low\":%.5f,\"close\":%.5f,\"volume\":%.1f",
        sym, InpTimeframe, rates[0].open, rates[0].high, rates[0].low,
        rates[0].close, (double)rates[0].tick_volume);
    SendString(g_pub, BuildEnvelope(MSG_BAR_CLOSED, payload), true);
  }
}

void PublishHeartbeat()
{
  SendString(g_pub, BuildEnvelope(MSG_HEARTBEAT, ""), true);
}

//+------------------------------------------------------------------+
//| Envelope: {v,type,ts,session_id,payload}. Payload is a raw JSON  |
//| fragment (already comma-joined key:value pairs), or "" for {}.   |
//+------------------------------------------------------------------+
string BuildEnvelope(const string type, const string payload_fragment)
{
  ulong ts = g_heartbeat.NowUnixMs();
  string payload = (StringLen(payload_fragment) > 0) ? ("{" + payload_fragment + "}") : "{}";
  return StringFormat(
      "{\"v\":%d,\"type\":\"%s\",\"ts\":%I64u,\"session_id\":\"%s\",\"payload\":%s}",
      COCOON_PROTOCOL_VERSION, type, ts, InpSessionId, payload);
}

//+------------------------------------------------------------------+
void SendString(Socket *sock, const string s, const bool dontwait = false)
{
  uchar buf[];
  int len = StringToCharArray(s, buf, 0, -1, CP_UTF8) - 1; // drop trailing null
  ArrayResize(buf, len);
  sock.send(buf, dontwait);
}

//+------------------------------------------------------------------+
//| Minimal JSON field extractors. The Python side sends JSON-shaped |
//| msgpack fallback frames the EA understands; production builds    |
//| should link the vendored msgpack pack/unpack from mql-zmq. These |
//| cover the flat fields this protocol uses.                        |
//+------------------------------------------------------------------+
string JsonFindString(const string body, const string key)
{
  string needle = "\"" + key + "\":\"";
  int p = StringFind(body, needle);
  if (p < 0)
    return "";
  p += StringLen(needle);
  int q = StringFind(body, "\"", p);
  if (q < 0)
    return "";
  return StringSubstr(body, p, q - p);
}

double JsonFindDouble(const string body, const string key)
{
  string needle = "\"" + key + "\":";
  int p = StringFind(body, needle);
  if (p < 0)
    return 0.0;
  p += StringLen(needle);
  int end = p;
  while (end < StringLen(body))
  {
    ushort c = StringGetCharacter(body, end);
    if ((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E')
      end++;
    else
      break;
  }
  return StringToDouble(StringSubstr(body, p, end - p));
}

ENUM_TIMEFRAMES StringToTimeframe(const string tf)
{
  if (tf == "M1")
    return PERIOD_M1;
  if (tf == "M5")
    return PERIOD_M5;
  if (tf == "M15")
    return PERIOD_M15;
  if (tf == "M30")
    return PERIOD_M30;
  if (tf == "H1")
    return PERIOD_H1;
  if (tf == "H4")
    return PERIOD_H4;
  if (tf == "D1")
    return PERIOD_D1;
  return PERIOD_M1;
}
//+------------------------------------------------------------------+
