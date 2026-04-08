# Services: test-service, platform-master (via /api)
# Local dev — direct container access

# Platform Master API
handle_path /api/* {
    reverse_proxy http://platform-master:8000 {
        header_up X-Real-IP {remote_host}
    }
}

@test-service path /test/*

handle @test-service {
    uri strip_prefix /test
    reverse_proxy http://test-service:80 {
        header_up X-Real-IP {remote_host}
        header_up X-Service-Name test-service
    }
}

# Fallback
handle {
    respond "🚗 Platform local dev is running!\n" 200
}
