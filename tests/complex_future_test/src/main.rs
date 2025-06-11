use core::future::{Future, poll_fn};
use core::pin::Pin;
use core::task::{Context, Poll, Waker};

// The no-std future example demonstrates several important aspects of futures:
// 1. Nested future execution
// 2. Parallel computation patterns
// 3. Recursive future patterns
// 4. Sequential and parallel task scheduling
// 5. Proper yielding and resumption of tasks
// Each task shows different patterns of future composition and execution, making it a good test case for verifying the executor's behavior with complex future patterns. 



fn main() {
    spawn(complex_task1());
    spawn(complex_task2());
    spawn(complex_task3());
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

// A future that simulates a computation with multiple steps
async fn compute_step(value: u32, steps: u32) -> u32 {
    let mut result = value;
    for i in 0..steps {
        println!("Computing step {} for value {}", i + 1, value);
        yield_now().await;
        result += 1;
    }
    result
}

// A future that combines multiple computations
async fn combine_results(a: u32, b: u32) -> u32 {
    let a_result = compute_step(a, 2).await;
    let b_result = compute_step(b, 3).await;
    a_result + b_result
}

// Complex task 1: Demonstrates nested futures with sequential and parallel computation
async fn complex_task1() {
    println!("Starting complex task 1");
    
    // Sequential computation
    let result1 = compute_step(1, 2).await;
    println!("Sequential computation result: {}", result1);
    
    // Nested computation
    let result2 = combine_results(2, 3).await;
    println!("Nested computation result: {}", result2);
    
    // Final computation
    let final_result = compute_step(result1 + result2, 1).await;
    println!("Complex task 1 final result: {}", final_result);
}

// Complex task 2: Demonstrates branching futures
async fn complex_task2() {
    println!("Starting complex task 2");
    
    // Branch 1
    let branch1 = async {
        let a = compute_step(5, 1).await;
        let b = compute_step(6, 1).await;
        a + b
    };
    
    // Branch 2
    let branch2 = async {
        let a = compute_step(7, 2).await;
        let b = compute_step(8, 1).await;
        a * b
    };
    
    // Execute branches
    let result1 = branch1.await;
    let result2 = branch2.await;
    
    println!("Complex task 2 results - Branch1: {}, Branch2: {}", result1, result2);
}

// Complex task 3: Demonstrates recursive future pattern
async fn complex_task3() {
    println!("Starting complex task 3");
    
    fn recursive_compute(n: u32, depth: u32) -> Pin<Box<dyn Future<Output = u32> + Send>> {
        Box::pin(async move {
            if depth == 0 {
                return n;
            }
            
            let a = recursive_compute(n + 1, depth - 1).await;
            let b = recursive_compute(n + 2, depth - 1).await;
            
            compute_step(a + b, 1).await
        })
    }
    
    let result = recursive_compute(1, 2).await;
    println!("Complex task 3 recursive result: {}", result);
} 