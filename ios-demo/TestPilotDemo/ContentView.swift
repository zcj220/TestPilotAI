import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        if model.isLoggedIn {
            HomeView()
        } else {
            LoginView()
        }
    }
}
