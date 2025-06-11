use core::future::{Future, poll_fn};
use core::pin::Pin;
use core::task::{Context, Poll, Waker};

// simple no-std future example

fn main() {
    spawn(test1());
    spawn(test2());
    spawn(test3());
    run();
}

pub struct Executor {
    pub tasks: Vec<Pin<Box<dyn Future<Output = ()> + Send + 'static>>>,
}

static mut EXECUTOR: Executor = Executor { tasks: Vec::new() };

fn spawn<F>(f: F)
where
    F: Future<Output = ()> + Send + 'static,
{
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(Box::pin(f));
}

fn pick_next_task() -> Option<Pin<Box<dyn Future<Output = ()> + Send + 'static>>> {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.pop()
}

fn put_prev_task(task: Pin<Box<dyn Future<Output = ()> + Send + 'static>>) {
    let executor = unsafe { &mut *(&raw mut EXECUTOR) };
    executor.tasks.push(task)
}

async fn yield_now() {
    let mut flag = false;
    poll_fn(|_cx| {
        if !flag {
            flag = true;
            Poll::Pending
        } else {
            Poll::Ready(())
        }
    })
    .await;
}

fn run() {
    let waker = Waker::noop();
    let mut cx = Context::from_waker(&waker);
    loop {
        if let Some(mut task) = pick_next_task() {
            match task.as_mut().poll(&mut cx) {
                Poll::Pending => {
                    put_prev_task(task);
                }
                Poll::Ready(_) => {}
            }
        } else {
            break;
        }
    }
}

async fn test1() {
    println!("run test task 1");
    yield_now().await;
    println!("run test task 1 done");
}

async fn test2() {
    println!("run test task 2");
}

async fn test3() {
    println!("run test task 3");
} 