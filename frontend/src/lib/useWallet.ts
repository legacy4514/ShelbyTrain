"use client";
import { useWallet as useAptosWallet } from "@aptos-labs/wallet-adapter-react";
import { useCallback, useEffect, useMemo } from "react";

function getWalletAddress(account: ReturnType<typeof useAptosWallet>["account"]) {
  return account?.address?.toString() ?? null;
}

export function useWallet() {
  const {
    account,
    connect: connectWallet,
    connected,
    disconnect: disconnectWallet,
    hiddenWallets,
    isLoading,
    wallet,
    wallets,
  } = useAptosWallet();

  const availableWallets = useMemo(
    () => [...wallets, ...hiddenWallets],
    [hiddenWallets, wallets],
  );

  const preferredWallet = useMemo(() => {
    return (
      availableWallets.find((availableWallet) => availableWallet.name === "Petra") ??
      availableWallets[0] ??
      null
    );
  }, [availableWallets]);

  const connect = useCallback(async () => {
    if (!preferredWallet) {
      window.open("https://petra.app/", "_blank", "noopener,noreferrer");
      return;
    }

    await Promise.resolve(connectWallet(preferredWallet.name));
  }, [connectWallet, preferredWallet]);

  const disconnect = useCallback(async () => {
    await Promise.resolve(disconnectWallet());
  }, [disconnectWallet]);

  const address = getWalletAddress(account);

  useEffect(() => {
    const target = window as Window & { __shelby_wallet_address?: string | null };
    target.__shelby_wallet_address = address;
    return () => {
      if (target.__shelby_wallet_address === address) {
        target.__shelby_wallet_address = null;
      }
    };
  }, [address]);

  return {
    connected,
    address,
    connecting: isLoading,
    connect,
    disconnect,
    walletName: wallet?.name ?? preferredWallet?.name ?? null,
    hasWallet: availableWallets.length > 0,
    walletChecked: !isLoading,
  };
}
