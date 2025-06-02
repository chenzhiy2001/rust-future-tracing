use std::thread;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("[{:?}] Main async block START", thread::current().id());
    let mut url_groups = Vec::new();
    url_groups.push("https://config.net.cn/tools/ProvinceCityCountry.html");

    for a_url in url_groups {
        println!("[{:?}] Loop iteration START for URL: {}", thread::current().id(), a_url);
        println!("[{:?}] INFO start to add a spider on: {}", thread::current().id(), a_url);
        println!("[{:?}] before reqwest::get time: {:?}", thread::current().id(), std::time::SystemTime::now());
        
        println!("[{:?}] PRE-AWAIT reqwest::get for URL: {}", thread::current().id(), a_url);
        let response = reqwest::get(a_url).await?;
        println!("[{:?}] POST-AWAIT reqwest::get for URL: {}. Status: {}", thread::current().id(), a_url, response.status());
        
        println!("[{:?}] after reqwest::get await time: {:?}", thread::current().id(), std::time::SystemTime::now());
        
        println!("[{:?}] PRE-AWAIT response.text() for URL: {}", thread::current().id(), a_url);
        let html_body = response.text().await?;
        println!("[{:?}] POST-AWAIT response.text() for URL: {}", thread::current().id(), a_url);
        
        println!("[{:?}] got html_body, length = {} time: {:?}", thread::current().id(), html_body.len(), std::time::SystemTime::now());
        //println!("html_body = {html_body:?}");
        println!("[{:?}] Loop iteration END for URL: {}", thread::current().id(), a_url);
    }
    println!("[{:?}] Main async block END", thread::current().id());
    Ok(())
}