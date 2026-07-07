//! Concurrency primitives shared by the interpreter (and, later, compiled code).
//!
//! The model is Go/Swift inspired: lightweight *tasks* (here backed by OS threads
//! for real parallelism), typed *channels* for message passing, and join handles
//! that power `await` and structured task groups.

use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

pub use crossbeam_channel::{Receiver, Select, Sender};

/// A typed channel: a cloneable `(Sender, Receiver)` pair.
pub struct Channel<T> {
    pub tx: Sender<T>,
    pub rx: Receiver<T>,
}

impl<T> Clone for Channel<T> {
    fn clone(&self) -> Self {
        Channel {
            tx: self.tx.clone(),
            rx: self.rx.clone(),
        }
    }
}

impl<T: Send> Channel<T> {
    /// Unbounded channel.
    pub fn unbounded() -> Channel<T> {
        let (tx, rx) = crossbeam_channel::unbounded();
        Channel { tx, rx }
    }

    /// Bounded channel with the given capacity (0 = rendezvous).
    pub fn bounded(cap: usize) -> Channel<T> {
        let (tx, rx) = crossbeam_channel::bounded(cap);
        Channel { tx, rx }
    }

    pub fn send(&self, v: T) -> bool {
        self.tx.send(v).is_ok()
    }

    pub fn recv(&self) -> Option<T> {
        self.rx.recv().ok()
    }

    pub fn try_recv(&self) -> Option<T> {
        self.rx.try_recv().ok()
    }
}

/// A spawned task whose result can be `await`ed (joined) exactly once.
pub struct Task<T> {
    handle: Mutex<Option<JoinHandle<T>>>,
    result: Mutex<Option<T>>,
}

impl<T: Send + 'static> Task<T> {
    pub fn spawn(f: impl FnOnce() -> T + Send + 'static) -> Arc<Task<T>> {
        let handle = std::thread::spawn(f);
        Arc::new(Task {
            handle: Mutex::new(Some(handle)),
            result: Mutex::new(None),
        })
    }

    /// Block until the task finishes, returning a clone of its result.
    pub fn join(&self) -> T
    where
        T: Clone,
    {
        let mut handle = self.handle.lock().unwrap();
        if let Some(h) = handle.take() {
            let r = h.join().unwrap_or_else(|_| panic!("task panicked"));
            *self.result.lock().unwrap() = Some(r);
        }
        self.result.lock().unwrap().clone().expect("task result")
    }
}
