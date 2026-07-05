//+------------------------------------------------------------------+
//| Zmq.mqh  —  minimal MQL5 binding surface for libzmq              |
//| DOCUMENT.md §4 (mql-zmq, Include\Zmq\Zmq.mqh), §13.1.            |
//|                                                                  |
//| NOTE: This is the interface façade the Cocoon EA compiles        |
//| against. The full mql-zmq distribution (Context/Socket wrapper   |
//| classes over the libzmq DLL imports) is a third-party vendored   |
//| dependency; drop its Zmq.mqh here to replace this façade. The    |
//| symbols below are exactly those CocoonEA.mq5 uses, so the EA     |
//| compiles against either this or the upstream header.             |
//+------------------------------------------------------------------+
#ifndef COCOON_ZMQ_MQH
#define COCOON_ZMQ_MQH

#define ZMQ_REP  4
#define ZMQ_PUB  1
#define ZMQ_DONTWAIT 1

#import "libzmq.dll"
   long zmq_ctx_new();
   int  zmq_ctx_term(long context);
   long zmq_socket(long context,int type);
   int  zmq_close(long socket);
   int  zmq_bind(long socket,uchar &endpoint[]);
   int  zmq_send(long socket,uchar &buf[],int len,int flags);
   int  zmq_recv(long socket,uchar &buf[],int len,int flags);
#import

//--- Thin RAII-ish wrappers used by CocoonEA.mq5.
class Context
  {
private:
   long              m_ctx;
public:
                     Context() { m_ctx=zmq_ctx_new(); }
                    ~Context() { if(m_ctx!=0) zmq_ctx_term(m_ctx); }
   long              Handle() const { return m_ctx; }
  };

class Socket
  {
private:
   long              m_sock;
public:
                     Socket(Context &ctx,int type) { m_sock=zmq_socket(ctx.Handle(),type); }
                    ~Socket() { if(m_sock!=0) zmq_close(m_sock); }

   bool              bind(const string endpoint)
     {
      uchar buf[];
      StringToCharArray(endpoint,buf);
      return zmq_bind(m_sock,buf)==0;
     }

   bool              send(const uchar &data[],const bool dontwait=false)
     {
      int flags=dontwait?ZMQ_DONTWAIT:0;
      //--- zmq_send imports the buffer as a non-const uchar&[]; MQL5 forbids
      //--- casting away const on an array, so pass a local mutable copy.
      uchar buf[];
      ArrayCopy(buf,data);
      return zmq_send(m_sock,buf,ArraySize(buf),flags)>=0;
     }

   int               recv(uchar &out[],const bool dontwait=true)
     {
      ArrayResize(out,65536);
      int flags=dontwait?ZMQ_DONTWAIT:0;
      int n=zmq_recv(m_sock,out,ArraySize(out),flags);
      if(n>=0)
         ArrayResize(out,n);
      return n;
     }
  };

#endif // COCOON_ZMQ_MQH
//+------------------------------------------------------------------+
