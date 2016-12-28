use std::net::SocketAddr;
use std::sync::Arc;

use tokio_core::io::Io;
use minihttp::Status;
use minihttp::server::{Dispatcher, Error, Head};

use config::ConfigCell;
use runtime::Runtime;
use incoming::{Request, Debug, Input};
use routing::{parse_host, route};
use default_error_page::error_page;


pub struct Router {
    addr: SocketAddr,
    runtime: Arc<Runtime>,
}

impl Router {
    pub fn new(addr: SocketAddr, runtime: Arc<Runtime>) -> Router {
        Router {
            addr: addr,
            runtime: runtime,
        }
    }
}

impl<S: Io + 'static> Dispatcher<S> for Router {
    type Codec = Request<S>;
    fn headers_received(&mut self, headers: &Head)
        -> Result<Self::Codec, Error>
    {
        // Keep config same while processing a single request
        let cfg = self.runtime.config.get();
        let mut debug = Debug::new(headers, &cfg);

        // No path means either CONNECT host, or OPTIONS *
        // in both cases we use root route for the domain to make decision
        //
        // TODO(tailhook) strip ?, #, ; from path
        let path = headers.path().unwrap_or("/");

        let matched_route = headers.host().map(parse_host)
            .and_then(|host| route(host, &path, &cfg.routing));
        let (handler, pref, suf) = if let Some((route, p, s)) = matched_route {
            debug.set_route(route);
            (cfg.handlers.get(route), p, s)
        } else {
            (None, "", path)
        };
        let inp = Input {
            addr: self.addr,
            runtime: &self.runtime,
            config: &cfg,
            debug: debug,
            headers: headers,
            prefix: pref,
            suffix: suf,
        };
        if let Some(handler) = handler {
            handler.serve(inp)
        } else {
            Ok(error_page(Status::NotFound, inp))
        }
    }
}