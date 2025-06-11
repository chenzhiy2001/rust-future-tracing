use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};

// simple std future example

// A simple future that returns a number after some computation
struct NumberFuture {
    value: u32,
    processed: bool,
}

impl NumberFuture {
    fn new(value: u32) -> Self {
        NumberFuture {
            value,
            processed: false,
        }
    }
}

impl Future for NumberFuture {
    type Output = u32;

    fn poll(mut self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> {
        if !self.processed {
            // Simulate some computation
            self.processed = true;
            Poll::Pending
        } else {
            Poll::Ready(self.value)
        }
    }
}

// A future that adds two numbers
async fn add_future(a: u32, b: u32) -> u32 {
    let a_future = NumberFuture::new(a);
    let b_future = NumberFuture::new(b);
    
    let a_result = a_future.await;
    let b_result = b_future.await;
    
    a_result + b_result
}

// A future that multiplies a number by 2
async fn double_future(n: u32) -> u32 {
    let n_future = NumberFuture::new(n);
    let result = n_future.await;
    result * 2
}

// Main async function that chains futures
async fn compute_result() -> u32 {
    let sum = add_future(5, 3).await;
    double_future(sum).await
}

// A simple runtime to execute our futures
struct SimpleRuntime {
    tasks: Vec<Pin<Box<dyn Future<Output = ()> + 'static>>>,
}

impl SimpleRuntime {
    fn new() -> Self {
        SimpleRuntime { tasks: Vec::new() }
    }

    fn spawn<F>(&mut self, future: F)
    where
        F: Future<Output = ()> + 'static,
    {
        self.tasks.push(Box::pin(future));
    }

    fn run(&mut self) {
        while !self.tasks.is_empty() {
            let mut i = 0;
            while i < self.tasks.len() {
                let task = &mut self.tasks[i];
                let waker = futures::task::noop_waker();
                let mut cx = Context::from_waker(&waker);
                
                match task.as_mut().poll(&mut cx) {
                    Poll::Ready(_) => {
                        self.tasks.remove(i);
                    }
                    Poll::Pending => {
                        i += 1;
                    }
                }
            }
        }
    }
}

fn main() {
    let mut runtime = SimpleRuntime::new();
    
    // Spawn our computation
    runtime.spawn(async {
        let result = compute_result().await;
        println!("Final result: {}", result);
    });
    
    // Run the runtime
    runtime.run();
}
