import Foundation

struct AgentLoginResponse: Decodable {
    let token: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
    }
}

enum AgentAPI {
    static func login(
        serverURL: URL,
        username: String,
        password: String
    ) async throws -> AgentLoginResponse {
        let url = serverURL
            .appending(path: "api")
            .appending(path: "v1")
            .appending(path: "auth")
            .appending(path: "agent")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "username": username,
            "password": password,
        ])
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200 ..< 300).contains(http.statusCode)
        else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw AgentAPIError.requestFailed(detail ?? "登录失败")
        }
        return try JSONDecoder().decode(AgentLoginResponse.self, from: data)
    }
}

enum AgentAPIError: Error, CustomStringConvertible {
    case requestFailed(String)

    var description: String {
        switch self {
        case let .requestFailed(message): message
        }
    }
}
