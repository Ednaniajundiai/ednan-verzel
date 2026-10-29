import { Route, Routes } from 'react-router-dom';
import { AuditPage } from './audit/AuditPage';
import { RequireRole } from './auth/RequireRole';
import { SalaPage } from './features/sala/SalaPage';
import { VitrinePage } from './features/vitrine/VitrinePage';
import { Layout } from './layout/Layout';
import { NewLotPage } from './pages/auctioneer/LotForm';
import { MyBidsPage } from './participations/MyBidsPage';
import { ReceiptPage } from './receipt/ReceiptPage';
import { PanelPage } from './pages/auctioneer/PanelPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { WalletPage } from './wallet/WalletPage';

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<VitrinePage />} />
        <Route path="/lotes/:id" element={<SalaPage />} />
        <Route path="/entrar" element={<LoginPage />} />
        <Route path="/cadastro" element={<RegisterPage />} />
        <Route
          path="/painel"
          element={
            <RequireRole role="auctioneer">
              <PanelPage />
            </RequireRole>
          }
        />
        <Route
          path="/painel/novo"
          element={
            <RequireRole role="auctioneer">
              <NewLotPage />
            </RequireRole>
          }
        />
        {/* Reservadas para a spec 004. */}
        <Route
          path="/carteira"
          element={
            <RequireRole role="bidder">
              <WalletPage />
            </RequireRole>
          }
        />
        <Route
          path="/arremates"
          element={
            <RequireRole role="bidder">
              <MyBidsPage />
            </RequireRole>
          }
        />
        <Route path="/auditoria/:id" element={<AuditPage />} />
        <Route path="/comprovante/:id" element={<ReceiptPage />} />
        <Route path="*" element={<p>Página não encontrada.</p>} />
      </Routes>
    </Layout>
  );
}
